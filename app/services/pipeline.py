from __future__ import annotations

import logging
import time
from pathlib import Path

from app.core.config import settings
from app.schemas import AudioFormat, JobStage, JobStatus
from app.services.document_extractor import extract_text
from app.services.fine_tune import fine_tune_text
from app.services.jobs import job_store
from app.services.tts.registry import get_engine

logger = logging.getLogger(__name__)


def process_job(job_id: str) -> None:
    """Run extract → fine-tune → TTS pipeline for a job."""
    job = job_store.get(job_id)
    if job is None:
        return

    t0 = time.perf_counter()
    try:
        job_store.update(job_id, status=JobStatus.processing, stage=JobStage.extract)
        t = time.perf_counter()
        upload = Path(job.meta["upload_path"])
        text = extract_text(upload)
        extract_ms = (time.perf_counter() - t) * 1000

        job_store.update(job_id, stage=JobStage.fine_tune)
        t = time.perf_counter()
        special = job.meta.get("special_words") or {}
        tuned = fine_tune_text(
            text,
            special_words=special,
            lexicon_path=settings.lexicon_path,
        )
        fine_tune_ms = (time.perf_counter() - t) * 1000
        refreshed = job_store.get(job_id)
        meta = dict(refreshed.meta) if refreshed else dict(job.meta)
        meta["char_count"] = len(tuned)
        meta["preview"] = tuned[:200]
        job_store.update(job_id, meta=meta)

        job_store.update(job_id, stage=JobStage.tts)
        audio_format = AudioFormat(job.audio_format) if job.audio_format else AudioFormat.wav
        engine_name = job.engine or ""
        version = job.version
        engine, resolved_name, resolved_version = get_engine(engine_name, version)
        job_store.update(job_id, engine=resolved_name, version=resolved_version)

        t = time.perf_counter()
        out_base = settings.audio_dir / job_id
        audio_path = engine.synthesize(tuned, out_base, audio_format.value)  # type: ignore[attr-defined]
        tts_ms = (time.perf_counter() - t) * 1000
        audio_url = f"/files/{audio_path.name}"

        refreshed = job_store.get(job_id)
        meta = dict(refreshed.meta) if refreshed else dict(job.meta)
        if resolved_name == "gemini":
            meta["gemini_voice"] = getattr(engine, "voice", None)
            meta["gemini_model"] = getattr(engine, "model", None)
            meta["gemini_backend"] = getattr(engine, "backend", None)
        elif resolved_name == "google_studio":
            meta["transport"] = "apps_script"
        meta["timing_ms"] = {
            "extract": round(extract_ms, 1),
            "fine_tune": round(fine_tune_ms, 1),
            "tts": round(tts_ms, 1),
            "total": round((time.perf_counter() - t0) * 1000, 1),
        }
        job_store.update(job_id, audio_url=audio_url, meta=meta)
        logger.info(
            "Job %s timing extract=%.0fms fine_tune=%.0fms tts=%.0fms chars=%s engine=%s",
            job_id,
            extract_ms,
            fine_tune_ms,
            tts_ms,
            len(tuned),
            resolved_name,
        )

        job_store.update(
            job_id,
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
