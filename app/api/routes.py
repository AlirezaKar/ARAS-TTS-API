from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app import __version__
from app.core.config import settings
from app.schemas import (
    AudioFormat,
    FeedbackRequest,
    FeedbackResponse,
    FineTunePreviewRequest,
    FineTunePreviewResponse,
    HealthResponse,
    JobCreateResponse,
    JobResponse,
    JobStatus,
)
from app.services.fine_tune import fine_tune_text, strip_harakat, validate_diacritized
from app.services.jobs import job_store
from app.services.pipeline import process_job
from app.services.pronunciation.db import init_schema, insert_pending
from app.services.tts.registry import ENGINE_ORDER, get_engine, list_engines, normalize_engine

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
    engine: str = Form(...),
    version: str | None = Form(None),
    audio_format: AudioFormat = Form(AudioFormat.wav),
    special_words: str | None = Form(None),
    special_words_file: UploadFile | None = File(None),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in settings.allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: .txt, .pdf, .docx",
        )

    eng_name = normalize_engine(engine)
    if eng_name not in ENGINE_ORDER:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown engine '{engine}'. Known: {', '.join(ENGINE_ORDER)}",
        )

    ver = version.strip() if version and version.strip() else None

    # Fail fast if engine/version cannot run (no silent fallbacks)
    try:
        get_engine(eng_name, ver)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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

    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    upload_name = f"{uuid.uuid4()}{suffix}"
    upload_path = settings.uploads_dir / upload_name
    with upload_path.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    job = job_store.create(
        engine=eng_name,
        version=ver,
        audio_format=audio_format,
        upload_path=str(upload_path),
        special_words=words,
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
