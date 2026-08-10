from __future__ import annotations

from pathlib import Path

import httpx

from app.core.config import settings
from app.schemas import ElevenLabsModelVersion
from app.services.tts.base import ensure_parent

# User-facing version → ElevenLabs model_id (higher version = more advanced)
ELEVENLABS_VERSION_MAP: dict[str, str] = {
    ElevenLabsModelVersion.v1.value: "eleven_flash_v2_5",
    ElevenLabsModelVersion.v2.value: "eleven_multilingual_v2",
    ElevenLabsModelVersion.v3.value: "eleven_v3",
}

# Also accept full model IDs from the API / env
KNOWN_MODEL_IDS = frozenset(ELEVENLABS_VERSION_MAP.values()) | {
    "eleven_multilingual_v1",
    "eleven_turbo_v2",
    "eleven_turbo_v2_5",
    "eleven_flash_v2",
}


def resolve_elevenlabs_model_id(value: str | None = None) -> str:
    """
    Resolve a version alias (v1/v2/v3) or raw model_id.
    Falls back to settings.elevenlabs_model_id, then multilingual v2.
    """
    raw = (value or settings.elevenlabs_model_id or ElevenLabsModelVersion.v2.value).strip()
    key = raw.lower()
    if key in ELEVENLABS_VERSION_MAP:
        return ELEVENLABS_VERSION_MAP[key]
    # Allow passing full model ids (preserve original casing ElevenLabs expects)
    if key in {m.lower() for m in KNOWN_MODEL_IDS} or key.startswith("eleven_"):
        return raw if raw.startswith("eleven_") else key
    raise ValueError(
        f"Unknown ElevenLabs model '{value}'. "
        f"Use v1|v2|v3 or a model_id like eleven_multilingual_v2."
    )


class ElevenLabsEngine:
    """ElevenLabs cloud TTS (premium tier)."""

    name = "elevenlabs"

    def __init__(self, model_id: str | None = None) -> None:
        self.model_id = resolve_elevenlabs_model_id(model_id)

    def is_available(self) -> tuple[bool, str]:
        if not settings.elevenlabs_api_key:
            return False, "ELEVENLABS_API_KEY not set"
        if not settings.elevenlabs_voice_id:
            return False, "ELEVENLABS_VOICE_ID not set"
        return (
            True,
            f"voice={settings.elevenlabs_voice_id} model={self.model_id} "
            f"(versions: v1=flash_v2_5, v2=multilingual_v2, v3=eleven_v3)",
        )

    def synthesize(self, text: str, out_path: Path, fmt: str) -> Path:
        ok, detail = self.is_available()
        if not ok:
            raise RuntimeError(detail)

        ensure_parent(out_path)
        fmt = fmt.lower().lstrip(".")
        # ElevenLabs returns mp3 by default
        target = out_path.with_suffix(".mp3" if fmt == "mp3" else ".mp3")
        url = (
            f"https://api.elevenlabs.io/v1/text-to-speech/"
            f"{settings.elevenlabs_voice_id}"
        )
        headers = {
            "xi-api-key": settings.elevenlabs_api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {"stability": 0.4, "similarity_boost": 0.8},
        }
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            target.write_bytes(resp.content)

        if fmt == "wav":
            # Convert mp3 -> wav via pydub
            try:
                from pydub import AudioSegment

                wav_path = out_path.with_suffix(".wav")
                AudioSegment.from_mp3(str(target)).export(str(wav_path), format="wav")
                target.unlink(missing_ok=True)
                return wav_path
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"ElevenLabs mp3->wav conversion failed: {exc}") from exc
        return target
