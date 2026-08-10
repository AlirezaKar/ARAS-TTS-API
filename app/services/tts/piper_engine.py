from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.services.tts.base import ensure_parent, finalize_format


class PiperEngine:
    """Stock Piper TTS (OHF / piper-tts) with a Persian voice model."""

    name = "piper"

    def __init__(self, model_path: Path | None = None) -> None:
        self.model_path = model_path or settings.piper_model_path

    def is_available(self) -> tuple[bool, str]:
        try:
            import piper  # noqa: F401
        except ImportError:
            return False, "piper-tts package not installed"
        if not self.model_path.exists():
            return (
                False,
                f"Piper model missing at {self.model_path}. "
                "Place a Persian .onnx voice in models/",
            )
        return True, f"model={self.model_path.name}"

    def synthesize(self, text: str, out_path: Path, fmt: str) -> Path:
        from piper import PiperVoice

        ok, detail = self.is_available()
        if not ok:
            raise RuntimeError(detail)

        ensure_parent(out_path)
        wav_path = out_path.with_suffix(".wav")
        voice = PiperVoice.load(str(self.model_path))
        with open(wav_path, "wb") as wav_file:
            # piper-tts API variants
            if hasattr(voice, "synthesize_wav"):
                voice.synthesize_wav(text, wav_file)
            else:
                import wave

                with wave.open(wav_file, "wb") as wf:
                    voice.synthesize(text, wf)

        return finalize_format(wav_path, fmt)
