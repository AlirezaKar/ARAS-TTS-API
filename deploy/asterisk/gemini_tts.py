#!/usr/bin/env python3
"""Call a published Google Apps Script web app (Gemini TTS) and write a WAV for Asterisk.

Usage on the Asterisk / Issabel host:

  export GOOGLE_APPS_SCRIPT_URL='https://script.google.com/macros/s/YOUR_SCRIPT_ID/exec'
  python3 gemini_tts.py 'سلام، خوش آمدید'
  python3 gemini_tts.py --text 'سلام' --out /var/lib/asterisk/sounds/custom/gemini_tts.wav

Dialplan can then Playback(custom/gemini_tts) after this script finishes.

Paste deploy/asterisk/Code.gs into Apps Script and deploy as Web app (Anyone).
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
import wave
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    print("ERROR: install requests (pip install requests)", file=sys.stderr)
    sys.exit(1)

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

DEFAULT_OUT = "/var/lib/asterisk/sounds/custom/gemini_tts.wav"
PCM_RATE = 24000


def pcm_to_wav_bytes(pcm: bytes, *, rate: int = PCM_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def ensure_wav(audio: bytes) -> bytes:
    """Gemini TTS often returns raw PCM; Asterisk Playback needs WAV."""
    if audio[:4] == b"RIFF":
        return audio
    if audio[:3] == b"ID3" or audio[:2] == b"\xff\xfb":
        # MP3 — leave as-is (Playback may need convert); prefer WAV path
        return audio
    return pcm_to_wav_bytes(audio)


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
    return base64.b64decode(cleaned)


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


def decode_audio(body: bytes) -> bytes:
    if body[:4] == b"RIFF" or body[:3] == b"ID3" or body[:2] == b"\xff\xfb":
        return body
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        raise SystemExit("ERROR: empty Apps Script body")
    if text.startswith("ERROR:"):
        raise SystemExit(text)
    if text.lstrip().lower().startswith(("<!doctype", "<html")):
        raise SystemExit(
            "ERROR: Apps Script returned HTML (check web-app deploy: Anyone + /exec URL).\n"
            "See deploy/asterisk/README.md and paste Code.gs from this folder."
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

    for cand in candidates:
        try:
            audio = _b64decode_clean(cand)
            if len(audio) >= 44:
                return ensure_wav(audio)
        except Exception:  # noqa: BLE001
            continue
    raise SystemExit(f"ERROR: could not decode audio. Preview: {text[:200]!r}")


def synthesize(text: str, url: str, out_path: Path, timeout: float = 180.0) -> Path:
    resp = requests.post(
        url,
        json={"text": text},
        headers={"Content-Type": "application/json"},
        timeout=timeout,
        allow_redirects=True,
    )
    if resp.status_code != 200:
        raise SystemExit(f"ERROR: HTTP {resp.status_code}: {resp.text[:400]}")
    try:
        audio = decode_audio(resp.content)
    except SystemExit as first:
        resp = requests.post(
            url,
            data={"text": text},
            timeout=timeout,
            allow_redirects=True,
        )
        if resp.status_code != 200:
            raise SystemExit(f"ERROR: HTTP {resp.status_code}: {resp.text[:400]}") from first
        audio = decode_audio(resp.content)
    if len(audio) < 44:
        raise SystemExit("ERROR: response too small to be audio")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(ensure_wav(audio))
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text_pos", nargs="?", help="Text to synthesize (positional)")
    parser.add_argument("--text", "-t", help="Text to synthesize")
    parser.add_argument(
        "--out",
        "-o",
        default=os.environ.get("ASTERISK_TTS_OUT", DEFAULT_OUT),
        help=f"Output WAV path (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("GOOGLE_APPS_SCRIPT_URL", ""),
        help="Apps Script web app URL (or set GOOGLE_APPS_SCRIPT_URL)",
    )
    args = parser.parse_args()
    text = (args.text or args.text_pos or "").strip()
    if not text:
        parser.error("provide text as positional arg or --text")
    url = (args.url or "").strip()
    if not url:
        parser.error("set GOOGLE_APPS_SCRIPT_URL or pass --url")

    path = synthesize(text, url, Path(args.out))
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
