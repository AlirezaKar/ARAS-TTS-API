from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Platform(str, Enum):
    bale = "bale"
    telegram = "telegram"
    whatsapp = "whatsapp"


class Accuracy(str, Enum):
    fast = "fast"
    balanced = "balanced"
    high = "high"
    premium = "premium"


class ElevenLabsModelVersion(str, Enum):
    """Selectable ElevenLabs TTS model tiers (higher = more advanced)."""

    v1 = "v1"  # Flash v2.5 — fastest / lowest latency
    v2 = "v2"  # Multilingual v2 — high quality (default)
    v3 = "v3"  # Eleven v3 — most advanced / expressive


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
    send = "send"
    done = "done"


class SendResult(BaseModel):
    platform: Platform | None = None
    success: bool = False
    detail: str = ""
    method: str | None = None  # bot | playwright | cloud_api


class JobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.queued


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    stage: JobStage = JobStage.queued
    accuracy: Accuracy | None = None
    engine: str | None = None
    platform: Platform | None = None
    phone_number: str | None = None
    audio_format: AudioFormat | None = None
    audio_url: str | None = None
    send: SendResult | None = None
    error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class EngineInfo(BaseModel):
    accuracy: Accuracy
    engine: str
    available: bool
    detail: str = ""


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


class MessageTestRequest(BaseModel):
    phone_number: str
    platform: Platform
    text: str = "تست ارسال از Persian TTS-API"
    audio_path: str | None = None
