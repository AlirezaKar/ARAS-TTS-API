from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AudioFormat(str, Enum):
    wav = "wav"
    mp3 = "mp3"


class JobStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class JobStage(str, Enum):
    queued = "queued"
    extract = "extract"
    fine_tune = "fine_tune"
    tts = "tts"
    done = "done"


class JobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.queued


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    stage: JobStage = JobStage.queued
    engine: str | None = None
    version: str | None = None
    audio_format: AudioFormat | None = None
    audio_url: str | None = None
    error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class EngineVersionInfo(BaseModel):
    id: str
    available: bool
    detail: str = ""


class EngineInfo(BaseModel):
    engine: str
    display_name: str
    available: bool
    detail: str = ""
    versions: list[EngineVersionInfo] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
    app: str
    version: str


class FineTunePreviewRequest(BaseModel):
    text: str
    special_words: dict[str, str] = Field(default_factory=dict)


class FineTunePreviewResponse(BaseModel):
    original: str
    tuned: str


class FeedbackRequest(BaseModel):
    word: str
    correct_harakat: str
    text_id: str | None = None
    context: str | None = None
    context_tag: str | None = None


class FeedbackResponse(BaseModel):
    ok: bool = True
    pending_id: int
    detail: str = "Queued in pending_corrections (not applied to live lexicon)"
