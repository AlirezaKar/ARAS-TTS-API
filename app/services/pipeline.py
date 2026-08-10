from __future__ import annotations

import logging
from pathlib import Path

from app.core.config import settings
from app.schemas import Accuracy, AudioFormat, JobStage, JobStatus, Platform
from app.services.document_extractor import extract_text
from app.services.fine_tune import fine_tune_text
from app.services.jobs import job_store
from app.services.messaging.registry import send_voice
from app.services.tts.registry import get_engine_for_accuracy

logger = logging.getLogger(__name__)


def process_job(job_id: str) -> None:
    """Run full extract → fine-tune → TTS → send pipeline for a job."""
    job = job_store.get(job_id)
    if job is None:
        return

    try:
        job_store.update(job_id, status=JobStatus.processing, stage=JobStage.extract)
        upload = Path(job.meta["upload_path"])
        text = extract_text(upload)

        job_store.update(job_id, stage=JobStage.fine_tune)
        special = job.meta.get("special_words") or {}
        tuned = fine_tune_text(
            text,
            special_words=special,
            lexicon_path=settings.lexicon_path,
        )
        refreshed = job_store.get(job_id)
        meta = dict(refreshed.meta) if refreshed else dict(job.meta)
        meta["char_count"] = len(tuned)
        meta["preview"] = tuned[:200]
        job_store.update(job_id, meta=meta)

        job_store.update(job_id, stage=JobStage.tts)
        accuracy = Accuracy(job.accuracy) if job.accuracy else Accuracy.balanced
        audio_format = AudioFormat(job.audio_format) if job.audio_format else AudioFormat.mp3
        elevenlabs_model = job.meta.get("elevenlabs_model")
        engine, engine_name = get_engine_for_accuracy(
            accuracy,
            elevenlabs_model=elevenlabs_model,
        )
        job_store.update(job_id, engine=engine_name)

        out_base = settings.audio_dir / job_id
        audio_path = engine.synthesize(tuned, out_base, audio_format.value)  # type: ignore[attr-defined]
        audio_url = f"/files/{audio_path.name}"
        # Record resolved ElevenLabs model when used
        if engine_name == "elevenlabs":
            refreshed = job_store.get(job_id)
            meta = dict(refreshed.meta) if refreshed else dict(job.meta)
            meta["elevenlabs_model_id"] = getattr(engine, "model_id", None)
            job_store.update(job_id, audio_url=audio_url, meta=meta)
        else:
            job_store.update(job_id, audio_url=audio_url)

        job_store.update(job_id, stage=JobStage.send)
        platform = Platform(job.platform) if job.platform else Platform.bale
        phone = job.phone_number or ""
        if settings.skip_messaging:
            from app.schemas import SendResult

            send_result = SendResult(
                platform=platform,
                success=True,
                detail="Messaging skipped (SKIP_MESSAGING=true)",
                method="skipped",
            )
        else:
            send_result = send_voice(
                platform,
                phone,
                audio_path,
                caption="فایل صوتی TTS",
            )
        job_store.update(
            job_id,
            send=send_result,
            stage=JobStage.done,
            status=JobStatus.completed,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Job %s failed", job_id)
        job_store.update(
            job_id,
            status=JobStatus.failed,
            error=str(exc),
        )
