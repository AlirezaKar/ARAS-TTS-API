from __future__ import annotations

import base64
import io
import json
import logging
import re
import time
import wave
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.services.tts.base import ensure_parent, finalize_format

logger = logging.getLogger(__name__)

_DATA_URI_RE = re.compile(
    r"data:audio/(?:wav|wave|x-wav|mpeg|mp3|x-mpeg-3|L16|pcm);base64,([A-Za-z0-9+/=\s]+)",
    re.IGNORECASE,
)
_BASE64_RUN_RE = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")
_JSON_AUDIO_KEYS = (
    "audio",
    "audioBase64",
    "audio_base64",
    "base64",
    "base64Audio",
    "data",
    "content",
    "result",
    "wav",
    "mp3",
)


def pcm_to_wav_bytes(pcm: bytes, *, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def ensure_wav(audio: bytes) -> bytes:
    if audio[:4] == b"RIFF":
        return audio
    if audio[:3] == b"ID3" or audio[:2] == b"\xff\xfb":
        return audio
    return pcm_to_wav_bytes(audio)


def _preview(text: str, limit: int = 240) -> str:
    one_line = re.sub(r"\s+", " ", text).strip()
    if len(one_line) > limit:
        return one_line[:limit] + "…"
    return one_line


def _looks_like_html(text: str) -> bool:
    head = text.lstrip()[:200].lower()
    return head.startswith("<!doctype") or head.startswith("<html") or "<body" in head


def _b64decode_clean(payload: str) -> bytes:
    cleaned = payload.strip()
    if cleaned.startswith("ERROR:"):
        raise ValueError(cleaned)
    m = _DATA_URI_RE.search(cleaned)
    if m:
        cleaned = m.group(1)
    cleaned = re.sub(r"\s+", "", cleaned)
    if not re.fullmatch(r"[A-Za-z0-9+/=]+", cleaned):
        raise ValueError("payload is not pure base64")
    if len(cleaned) < 16:
        raise ValueError("base64 payload too short")
    while len(cleaned) % 4 == 1:
        cleaned = cleaned[:-1]
    pad = (-len(cleaned)) % 4
    if pad:
        cleaned += "=" * pad
    return base64.b64decode(cleaned, validate=False)


def _extract_from_json(obj: Any) -> str | None:
    if isinstance(obj, str):
        s = obj.strip()
        if s.startswith("data:audio/") or (len(s) > 64 and re.fullmatch(r"[A-Za-z0-9+/=\s]+", s)):
            return s
        return None
    if isinstance(obj, dict):
        for key in _JSON_AUDIO_KEYS:
            if key in obj and isinstance(obj[key], str) and obj[key].strip():
                return obj[key]
        try:
            part = obj["candidates"][0]["content"]["parts"][0]
            if isinstance(part, dict):
                if isinstance(part.get("text"), str):
                    return part["text"]
                inline = part.get("inlineData") or part.get("inline_data")
                if isinstance(inline, dict) and isinstance(inline.get("data"), str):
                    return inline["data"]
        except (KeyError, IndexError, TypeError):
            pass
        for value in obj.values():
            found = _extract_from_json(value)
            if found:
                return found
    if isinstance(obj, list):
        for item in obj:
            found = _extract_from_json(item)
            if found:
                return found
    return None


def _riff_or_id3_runs(text: str) -> list[str]:
    found: list[str] = []
    for pattern in (r"UklGR[A-Za-z0-9+/]+=*", r"SUQz[A-Za-z0-9+/]+=*"):
        found.extend(re.findall(pattern, text))
    return found


def _strip_to_base64_if_mostly(text: str, *, min_len: int = 200, ratio: float = 0.97) -> str | None:
    compact = re.sub(r"\s+", "", text)
    if len(compact) < min_len:
        return None
    cleaned = re.sub(r"[^A-Za-z0-9+/=]", "", compact)
    if not cleaned or len(cleaned) / len(compact) < ratio:
        return None
    return cleaned


def decode_apps_script_audio(body: str | bytes) -> bytes:
    """Decode Apps Script web app response → WAV/MP3/PCM bytes."""
    if isinstance(body, bytes):
        if body[:4] == b"RIFF" or body[:3] == b"ID3" or body[:2] == b"\xff\xfb":
            return body
        text = body.decode("utf-8", errors="replace").strip()
    else:
        text = body.strip()

    if not text:
        raise RuntimeError("Apps Script returned an empty body")

    if _looks_like_html(text):
        raise RuntimeError(
            "Google Apps Script returned a login HTML page instead of audio. "
            "Redeploy the web app: Deploy → Web app → Execute as: Me, "
            "Who has access: Anyone, then use the /exec URL. "
            "Paste deploy/asterisk/Code.gs and put your AI Studio key inside Code.gs. "
            f"Preview: {_preview(text)}"
        )

    candidates: list[str] = []
    if text[:1] in "{[":
        try:
            extracted = _extract_from_json(json.loads(text))
            if extracted:
                candidates.append(extracted)
        except json.JSONDecodeError:
            pass
    for match in _DATA_URI_RE.finditer(text):
        candidates.append(match.group(0))
    compact = re.sub(r"\s+", "", text)
    candidates.extend(_riff_or_id3_runs(compact))
    if re.fullmatch(r"[A-Za-z0-9+/=]+", compact):
        candidates.append(compact)
    mostly = _strip_to_base64_if_mostly(text)
    if mostly:
        candidates.append(mostly)
    runs = _BASE64_RUN_RE.findall(compact)
    if runs:
        candidates.append(max(runs, key=len))

    seen: set[str] = set()
    ordered: list[str] = []
    for cand in candidates:
        if cand not in seen:
            seen.add(cand)
            ordered.append(cand)

    errors: list[str] = []
    for cand in ordered:
        try:
            audio = ensure_wav(_b64decode_clean(cand))
            if len(audio) >= 44:
                return audio
            errors.append(f"decoded {len(audio)} bytes")
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    raise RuntimeError(
        "Failed to decode Apps Script audio. "
        f"Tried {len(ordered)} candidate(s). Last errors: {errors[-3:]}. "
        f"Body preview: {_preview(text)}"
    )


def _write_audio_file(audio_bytes: bytes, out_path: Path, fmt: str) -> Path:
    """Write only the requested format (delete intermediates)."""
    ensure_parent(out_path.with_suffix(".wav"))
    desired = fmt.lower().lstrip(".")
    audio_bytes = ensure_wav(audio_bytes)

    if audio_bytes[:3] == b"ID3" or audio_bytes[:2] == b"\xff\xfb":
        if desired == "mp3":
            mp3_path = out_path.with_suffix(".mp3")
            mp3_path.write_bytes(audio_bytes)
            return mp3_path
        from pydub import AudioSegment

        from app.services.tts.base import configure_pydub_ffmpeg

        if not configure_pydub_ffmpeg():
            raise RuntimeError(
                "ffmpeg required to convert MP3→WAV "
                "(install system ffmpeg or: pip install imageio-ffmpeg)"
            )
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

    wav_path = out_path.with_suffix(".wav")
    wav_path.write_bytes(audio_bytes)
    return finalize_format(wav_path, "mp3")


class GoogleStudioEngine:
    """Google Studio TTS via published Apps Script web app only (no direct Gemini API)."""

    name = "google_studio"

    def is_available(self) -> tuple[bool, str]:
        url = settings.google_apps_script_url.strip()
        if not url:
            return (
                False,
                "GOOGLE_APPS_SCRIPT_URL not set — paste deploy/asterisk/Code.gs, "
                "deploy as Web app (Anyone), put /exec URL in .env",
            )
        short = f"{url[:48]}…" if len(url) > 48 else url
        return True, f"apps_script={short}"

    def synthesize(self, text: str, out_path: Path, fmt: str) -> Path:
        text = text.strip()
        if not text:
            raise ValueError("Empty text after fine-tune")

        url = settings.google_apps_script_url.strip()
        if not url:
            raise RuntimeError(
                "Set GOOGLE_APPS_SCRIPT_URL in .env (Apps Script /exec URL), then restart the API"
            )

        logger.info("Google Studio Apps Script TTS: chars=%s", len(text))
        t0 = time.perf_counter()
        with httpx.Client(timeout=300.0, follow_redirects=True) as client:
            resp = client.post(
                url,
                json={"text": text},
                headers={
                    "Content-Type": "application/json",
                    "Accept": "text/plain, application/json, */*",
                },
            )
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Apps Script HTTP {resp.status_code}: {resp.text[:500]}"
                )
            try:
                audio = decode_apps_script_audio(resp.content)
            except RuntimeError as exc:
                # HTML login / hard errors: do not double-wait with a form retry
                msg = str(exc).lower()
                if "html" in msg or "login" in msg or msg.startswith("error:"):
                    raise
                logger.info("JSON POST decode failed; retrying as form text=…")
                resp = client.post(url, data={"text": text})
                if resp.status_code >= 400:
                    raise RuntimeError(
                        f"Apps Script HTTP {resp.status_code}: {resp.text[:500]}"
                    ) from exc
                audio = decode_apps_script_audio(resp.content)

        http_ms = (time.perf_counter() - t0) * 1000
        logger.info("Google Studio Apps Script round-trip: %.0fms chars=%s", http_ms, len(text))

        if len(audio) < 44:
            raise RuntimeError("Apps Script returned too little audio data")
        return _write_audio_file(audio, out_path, fmt)
