from __future__ import annotations

import base64
import io
import json
import logging
import time
import wave
from pathlib import Path

import httpx

from app.core.config import settings
from app.services.tts.base import ensure_parent, finalize_format

logger = logging.getLogger(__name__)

# Cloud TTS model ids: https://docs.cloud.google.com/text-to-speech/docs/gemini-tts
# Developer API (AI Studio key) often uses the -preview-tts suffix.
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-preview-tts"
GEMINI_MODELS: tuple[str, ...] = (
    "gemini-2.5-flash-preview-tts",
    "gemini-2.5-flash-tts",
    "gemini-2.5-flash-lite-preview-tts",
    "gemini-3.1-flash-tts-preview",
    "gemini-2.5-pro-preview-tts",
    "gemini-2.5-pro-tts",
)

GEMINI_VOICES: tuple[str, ...] = (
    "Kore",
    "Puck",
    "Charon",
    "Zephyr",
    "Fenrir",
    "Aoede",
    "Leda",
    "Orus",
    "Callirrhoe",
    "Autonoe",
)

# TTS can take several minutes on free tier / long text; voice choice does not
# change availability — slow responses are usually quota/load, not a bad voice.
GEMINI_HTTP_TIMEOUT_S = 360.0


def pcm_to_wav_bytes(pcm: bytes, *, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def _write_audio(audio_bytes: bytes, out_path: Path, fmt: str) -> Path:
    """Write only the requested format (delete intermediates)."""
    ensure_parent(out_path.with_suffix(".wav"))
    desired = fmt.lower().lstrip(".")

    if audio_bytes[:4] != b"RIFF" and audio_bytes[:3] != b"ID3" and audio_bytes[:2] != b"\xff\xfb":
        audio_bytes = pcm_to_wav_bytes(audio_bytes)

    if audio_bytes[:3] == b"ID3" or audio_bytes[:2] == b"\xff\xfb":
        if desired == "mp3":
            mp3_path = out_path.with_suffix(".mp3")
            mp3_path.write_bytes(audio_bytes)
            return mp3_path
        # Convert MP3 → WAV only, keep WAV
        from pydub import AudioSegment

        from app.services.tts.base import configure_pydub_ffmpeg

        if not configure_pydub_ffmpeg():
            raise RuntimeError("ffmpeg required for MP3→WAV")
        tmp_mp3 = out_path.with_suffix(".tmp.mp3")
        wav_path = out_path.with_suffix(".wav")
        tmp_mp3.write_bytes(audio_bytes)
        try:
            AudioSegment.from_mp3(str(tmp_mp3)).export(str(wav_path), format="wav")
        finally:
            tmp_mp3.unlink(missing_ok=True)
        return wav_path

    if desired == "wav":
        wav_path = out_path.with_suffix(".wav")
        wav_path.write_bytes(audio_bytes)
        return wav_path

    # desired mp3: write temp wav then convert, delete wav
    wav_path = out_path.with_suffix(".wav")
    wav_path.write_bytes(audio_bytes)
    return finalize_format(wav_path, "mp3")


class GeminiEngine:
    """
    Direct Gemini TTS (independent of Apps Script / google_studio).

    Default backend: Gemini Developer API (AI Studio API key) — same family as
    Cloud Gemini-TTS Flash; see https://ai.google.dev/gemini-api/docs/speech-generation

    Optional backend: Cloud Text-to-Speech REST
    https://docs.cloud.google.com/text-to-speech/docs/gemini-tts
    (needs API key or OAuth + project; set GEMINI_TTS_BACKEND=cloud)
    """

    name = "gemini"

    def __init__(self, voice: str | None = None, model: str | None = None) -> None:
        self.voice = (voice or settings.gemini_voice or "Kore").strip() or "Kore"
        self.model = (
            model or settings.gemini_model or DEFAULT_GEMINI_MODEL
        ).strip() or DEFAULT_GEMINI_MODEL
        self.backend = (settings.gemini_tts_backend or "developer").strip().lower()
        self.prompt = (settings.gemini_prompt or "Say the following clearly.").strip()

    def is_available(self) -> tuple[bool, str]:
        if not settings.gemini_api_key.strip():
            return False, "GEMINI_API_KEY not set (AI Studio / Google AI key)"
        return True, f"backend={self.backend} model={self.model} voice={self.voice}"

    def synthesize(self, text: str, out_path: Path, fmt: str) -> Path:
        text = text.strip()
        if not text:
            raise ValueError("Empty text after fine-tune")
        if not settings.gemini_api_key.strip():
            raise RuntimeError("Set GEMINI_API_KEY in .env, then restart the API")

        t0 = time.perf_counter()
        if self.backend == "cloud":
            audio = self._synthesize_cloud_tts(text, fmt)
        else:
            audio = self._synthesize_developer_api(text)
        logger.info(
            "Gemini direct TTS: backend=%s model=%s voice=%s chars=%s ms=%.0f",
            self.backend,
            self.model,
            self.voice,
            len(text),
            (time.perf_counter() - t0) * 1000,
        )
        return _write_audio(audio, out_path, fmt)

    def _synthesize_developer_api(self, text: str) -> bytes:
        """Gemini API generateContent with AUDIO modality (API key)."""
        api_key = settings.gemini_api_key.strip()
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        # Optional style prompt prepended (Cloud TTS has a separate prompt field)
        spoken = text
        if self.prompt and not text.lower().startswith("say "):
            spoken = f"{self.prompt}\n\n{text}"

        payload = {
            "contents": [{"parts": [{"text": spoken}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": self.voice}
                    }
                },
            },
        }
        with httpx.Client(timeout=GEMINI_HTTP_TIMEOUT_S) as client:
            resp = client.post(
                url,
                headers={
                    "x-goog-api-key": api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if resp.status_code >= 400:
            raise RuntimeError(f"Gemini TTS HTTP {resp.status_code}: {resp.text[:800]}")

        data = resp.json()
        if data.get("error"):
            raise RuntimeError(f"Gemini TTS error: {data['error']}")

        try:
            part = data["candidates"][0]["content"]["parts"][0]
            inline = part.get("inlineData") or part.get("inline_data") or {}
            b64 = inline.get("data")
            mime = (inline.get("mimeType") or inline.get("mime_type") or "").lower()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"Unexpected Gemini response: {json.dumps(data)[:500]}"
            ) from exc

        if not b64:
            raise RuntimeError(f"Gemini response missing audio: {json.dumps(data)[:500]}")

        raw = base64.b64decode(b64)
        if raw[:4] == b"RIFF" or raw[:3] == b"ID3" or "wav" in mime:
            return raw
        return pcm_to_wav_bytes(raw)

    def _synthesize_cloud_tts(self, text: str, fmt: str) -> bytes:
        """
        Cloud Text-to-Speech text:synthesize (Gemini-TTS models).
        Docs: https://docs.cloud.google.com/text-to-speech/docs/gemini-tts
        Auth: API key (x-goog-api-key) and optional GOOGLE_CLOUD_PROJECT.
        """
        api_key = settings.gemini_api_key.strip()
        project = settings.google_cloud_project.strip()
        lang = (settings.gemini_language_code or "fa-IR").strip() or "fa-IR"
        encoding = "MP3" if fmt.lower().lstrip(".") == "mp3" else "LINEAR16"

        # Cloud docs often use gemini-2.5-flash-tts (no -preview-); map common alias
        model = self.model
        if model == "gemini-2.5-flash-preview-tts":
            model = "gemini-2.5-flash-tts"

        payload = {
            "input": {
                "prompt": self.prompt or "Say the following.",
                "text": text,
            },
            "voice": {
                "languageCode": lang,
                "name": self.voice,
                "modelName": model,
            },
            "audioConfig": {"audioEncoding": encoding},
        }

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        }
        if project:
            headers["x-goog-user-project"] = project

        url = "https://texttospeech.googleapis.com/v1/text:synthesize"
        with httpx.Client(timeout=GEMINI_HTTP_TIMEOUT_S) as client:
            resp = client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Cloud TTS HTTP {resp.status_code}: {resp.text[:800]}. "
                "Tip: free AI Studio keys usually need GEMINI_TTS_BACKEND=developer "
                "(default). Cloud TTS often requires a GCP project with billing."
            )

        data = resp.json()
        b64 = data.get("audioContent")
        if not b64:
            raise RuntimeError(f"Cloud TTS missing audioContent: {json.dumps(data)[:400]}")
        raw = base64.b64decode(b64)
        if encoding == "LINEAR16" and raw[:4] != b"RIFF":
            return pcm_to_wav_bytes(raw)
        return raw
