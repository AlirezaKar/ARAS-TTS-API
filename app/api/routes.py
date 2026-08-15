from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app import __version__
from app.core.config import settings
from app.schemas import (
    Accuracy,
    AudioFormat,
    ElevenLabsModelVersion,
    FeedbackRequest,
    FeedbackResponse,
    FineTunePreviewRequest,
    FineTunePreviewResponse,
    HealthResponse,
    JobCreateResponse,
    JobResponse,
    JobStatus,
    MessageTestRequest,
    Platform,
    SendResult,
)
from app.services.fine_tune import fine_tune_text, strip_harakat, validate_diacritized
from app.services.jobs import job_store
from app.services.messaging.base import normalize_phone
from app.services.messaging.phone_map import register_chat_id
from app.services.messaging.registry import send_voice
from app.services.pipeline import process_job
from app.services.pronunciation.db import init_schema, insert_pending
from app.services.tts.registry import list_engines

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", app=settings.app_name, version=__version__)


@router.get("/engines")
def engines():
    return {"engines": [e.model_dump() for e in list_engines()]}


@router.post("/tts", response_model=JobCreateResponse, status_code=202)
async def create_tts_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    phone_number: str = Form(...),
    platform: Platform = Form(...),
    accuracy: Accuracy = Form(Accuracy.balanced),
    audio_format: AudioFormat = Form(AudioFormat.mp3),
    special_words: str | None = Form(None),
    special_words_file: UploadFile | None = File(None),
    elevenlabs_model: ElevenLabsModelVersion | None = Form(None),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in settings.allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: .txt, .pdf, .docx",
        )

    words: dict[str, str] = {}
    if special_words:
        try:
            parsed = json.loads(special_words)
            if not isinstance(parsed, dict):
                raise ValueError("special_words must be a JSON object")
            words = {str(k): str(v) for k, v in parsed.items()}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Invalid special_words JSON: {exc}") from exc

    if special_words_file is not None and special_words_file.filename:
        try:
            raw = await special_words_file.read()
            parsed = json.loads(raw.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError("special_words_file must be a JSON object")
            words.update({str(k): str(v) for k, v in parsed.items()})
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=400, detail=f"Invalid special_words_file: {exc}"
            ) from exc

    phone = normalize_phone(phone_number)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)

    # Save upload
    import uuid

    upload_name = f"{uuid.uuid4()}{suffix}"
    upload_path = settings.uploads_dir / upload_name
    with upload_path.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    job = job_store.create(
        accuracy=accuracy,
        platform=platform,
        phone_number=phone,
        audio_format=audio_format,
        upload_path=str(upload_path),
        special_words=words,
        elevenlabs_model=elevenlabs_model.value if elevenlabs_model else None,
    )
    background_tasks.add_task(process_job, job.job_id)
    return JobCreateResponse(job_id=job.job_id, status=JobStatus.queued)


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str) -> JobResponse:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/files/{name}")
def get_file(name: str):
    # Prevent path traversal
    safe = Path(name).name
    path = settings.audio_dir / safe
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    media = "audio/mpeg" if path.suffix.lower() == ".mp3" else "audio/wav"
    return FileResponse(path, media_type=media, filename=safe)


@router.post("/fine-tune/preview", response_model=FineTunePreviewResponse)
def fine_tune_preview(body: FineTunePreviewRequest) -> FineTunePreviewResponse:
    tuned = fine_tune_text(
        body.text,
        special_words=body.special_words,
        lexicon_path=settings.lexicon_path,
    )
    return FineTunePreviewResponse(original=body.text, tuned=tuned)


@router.post("/feedback", response_model=FeedbackResponse)
def submit_feedback(body: FeedbackRequest) -> FeedbackResponse:
    """Queue a pronunciation correction. Does not mutate the live lexicon."""
    bare = strip_harakat(body.word.strip())
    if not bare:
        raise HTTPException(status_code=400, detail="word must contain Persian letters")
    harakat = validate_diacritized(body.correct_harakat.strip())
    if strip_harakat(harakat) != bare:
        raise HTTPException(
            status_code=400,
            detail="correct_harakat must be the same word with diacritics (letters must match)",
        )

    init_schema(settings.pronunciation_db_path)
    pending_id = insert_pending(
        settings.pronunciation_db_path,
        word=bare,
        proposed_harakat=harakat,
        source="user_report",
        confidence=0.9,
        detection_method="user_feedback",
        text_id=body.text_id,
        context=body.context,
        context_tag=body.context_tag,
    )
    return FeedbackResponse(ok=True, pending_id=pending_id)


@router.post("/messaging/test", response_model=SendResult)
def messaging_test(body: MessageTestRequest) -> SendResult:
    phone = normalize_phone(body.phone_number)
    if body.audio_path:
        path = Path(body.audio_path)
        if not path.is_absolute():
            path = settings.root_dir / path
        if not path.exists():
            raise HTTPException(status_code=400, detail="audio_path does not exist")
        return send_voice(body.platform, phone, path, caption=body.text)

    # Create a tiny placeholder text file as document if no audio
    # Prefer an existing sample audio; else write a text note as .txt attachment fail —
    # require audio for real send. For test without audio, write a short wav silence.
    sample = settings.audio_dir / "_messaging_test.wav"
    if not sample.exists():
        _write_silent_wav(sample)
    return send_voice(body.platform, phone, sample, caption=body.text)


@router.post("/phone-map")
def upsert_phone_map(
    phone_number: Annotated[str, Form()],
    platform: Annotated[Platform, Form()],
    chat_id: Annotated[str, Form()],
):
    phone = normalize_phone(phone_number)
    register_chat_id(phone, platform.value, chat_id)
    return {"ok": True, "phone_number": phone, "platform": platform, "chat_id": chat_id}


def _write_silent_wav(path: Path, seconds: float = 0.5, rate: int = 22050) -> None:
    import wave
    import struct

    path.parent.mkdir(parents=True, exist_ok=True)
    n = int(seconds * rate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack("<" + "h" * n, *([0] * n)))
