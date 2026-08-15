from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.schemas import AudioFormat, JobResponse, JobStage, JobStatus


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_job_data(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize legacy job JSON (accuracy/messaging era) for current schema."""
    if data.get("stage") == "send":
        data["stage"] = JobStage.done.value
    data.setdefault("version", None)
    data.pop("accuracy", None)
    data.pop("platform", None)
    data.pop("phone_number", None)
    data.pop("send", None)
    return data


class JobStore:
    """Disk-backed job metadata store with in-memory cache."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: dict[str, dict[str, Any]] = {}
        settings.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._load_existing()

    def _path(self, job_id: str) -> Path:
        return settings.jobs_dir / f"{job_id}.json"

    def _load_existing(self) -> None:
        for path in settings.jobs_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._cache[data["job_id"]] = _sanitize_job_data(data)
            except Exception:  # noqa: BLE001
                continue

    def create(
        self,
        *,
        engine: str,
        version: str | None,
        audio_format: AudioFormat,
        upload_path: str,
        special_words: dict[str, str],
    ) -> JobResponse:
        job_id = str(uuid.uuid4())
        now = _utcnow()
        meta: dict[str, Any] = {
            "upload_path": upload_path,
            "special_words": special_words,
        }
        data: dict[str, Any] = {
            "job_id": job_id,
            "status": JobStatus.queued.value,
            "stage": JobStage.queued.value,
            "engine": engine,
            "version": version,
            "audio_format": audio_format.value,
            "audio_url": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
            "meta": meta,
        }
        with self._lock:
            self._cache[job_id] = data
            self._persist(data)
        return JobResponse.model_validate(data)

    def get(self, job_id: str) -> JobResponse | None:
        with self._lock:
            data = self._cache.get(job_id)
            if data is None:
                path = self._path(job_id)
                if path.exists():
                    data = _sanitize_job_data(json.loads(path.read_text(encoding="utf-8")))
                    self._cache[job_id] = data
                else:
                    return None
            return JobResponse.model_validate(data)

    def update(self, job_id: str, **fields: Any) -> JobResponse:
        with self._lock:
            data = self._cache.get(job_id)
            if data is None:
                raise KeyError(job_id)
            for key, value in fields.items():
                if hasattr(value, "value"):
                    data[key] = value.value
                else:
                    data[key] = value
            data["updated_at"] = _utcnow()
            self._persist(data)
            return JobResponse.model_validate(data)

    def _persist(self, data: dict[str, Any]) -> None:
        path = self._path(data["job_id"])
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


job_store = JobStore()
