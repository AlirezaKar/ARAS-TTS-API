from __future__ import annotations

from pathlib import Path
from typing import Protocol


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


def convert_wav_to_mp3(wav_path: Path, mp3_path: Path) -> Path:
    """Convert WAV to MP3 using pydub if available, else copy wav and rename note."""
    ensure_parent(mp3_path)
    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_wav(str(wav_path))
        audio.export(str(mp3_path), format="mp3")
        return mp3_path
    except Exception as exc:  # noqa: BLE001
        # Fallback: keep wav and raise clear message if mp3 strictly required
        raise RuntimeError(
            f"MP3 conversion failed (install pydub + ffmpeg). Detail: {exc}"
        ) from exc


def finalize_format(wav_or_out: Path, desired_fmt: str) -> Path:
    """If engine produced wav and mp3 requested, convert."""
    desired_fmt = desired_fmt.lower().lstrip(".")
    if desired_fmt == "wav":
        if wav_or_out.suffix.lower() != ".wav":
            target = wav_or_out.with_suffix(".wav")
            wav_or_out.replace(target)
            return target
        return wav_or_out

    if desired_fmt == "mp3":
        if wav_or_out.suffix.lower() == ".mp3":
            return wav_or_out
        mp3_path = wav_or_out.with_suffix(".mp3")
        convert_wav_to_mp3(wav_or_out, mp3_path)
        return mp3_path

    raise ValueError(f"Unsupported audio format: {desired_fmt}")
