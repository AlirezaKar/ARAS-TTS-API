from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

_ffmpeg_configured = False


class TTSEngine(Protocol):
    name: str

    def is_available(self) -> tuple[bool, str]:
        """Return (available, detail)."""
        ...

    def synthesize(self, text: str, out_path: Path, fmt: str) -> Path:
        """Synthesize text to out_path (extension should match fmt)."""
        ...


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def configure_pydub_ffmpeg() -> str | None:
    """
    Point pydub at an ffmpeg binary.
    Prefer system PATH, then the imageio-ffmpeg wheel (Windows-friendly).
    """
    global _ffmpeg_configured
    from pydub import AudioSegment

    if _ffmpeg_configured and getattr(AudioSegment, "converter", None):
        return str(AudioSegment.converter)

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        try:
            import imageio_ffmpeg

            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as exc:  # noqa: BLE001
            logger.debug("imageio-ffmpeg unavailable: %s", exc)
            ffmpeg = None

    if not ffmpeg:
        return None

    AudioSegment.converter = ffmpeg
    AudioSegment.ffmpeg = ffmpeg
    AudioSegment.ffprobe = ffmpeg  # ffprobe not always separate; pydub mostly needs converter
    _ffmpeg_configured = True
    return ffmpeg


def convert_wav_to_mp3(wav_path: Path, mp3_path: Path) -> Path:
    """Convert WAV to MP3 using pydub if available, else copy wav and rename note."""
    ensure_parent(mp3_path)
    try:
        from pydub import AudioSegment

        if not configure_pydub_ffmpeg():
            raise RuntimeError(
                "ffmpeg not found (install system ffmpeg or: pip install imageio-ffmpeg)"
            )
        audio = AudioSegment.from_wav(str(wav_path))
        audio.export(str(mp3_path), format="mp3")
        return mp3_path
    except Exception as exc:  # noqa: BLE001
        # Fallback: keep wav and raise clear message if mp3 strictly required
        raise RuntimeError(
            f"MP3 conversion failed (install pydub + ffmpeg / imageio-ffmpeg). Detail: {exc}"
        ) from exc


def finalize_format(wav_or_out: Path, desired_fmt: str) -> Path:
    """Convert to desired format and keep only that file on disk."""
    desired_fmt = desired_fmt.lower().lstrip(".")
    if desired_fmt == "wav":
        if wav_or_out.suffix.lower() != ".wav":
            target = wav_or_out.with_suffix(".wav")
            if wav_or_out != target:
                wav_or_out.replace(target)
            return target
        return wav_or_out

    if desired_fmt == "mp3":
        if wav_or_out.suffix.lower() == ".mp3":
            return wav_or_out
        mp3_path = wav_or_out.with_suffix(".mp3")
        convert_wav_to_mp3(wav_or_out, mp3_path)
        # Prefer a single artifact: drop the intermediate WAV
        try:
            if wav_or_out.exists() and wav_or_out.resolve() != mp3_path.resolve():
                wav_or_out.unlink()
        except OSError:
            logger.debug("Could not remove intermediate WAV %s", wav_or_out)
        return mp3_path

    raise ValueError(f"Unsupported audio format: {desired_fmt}")
