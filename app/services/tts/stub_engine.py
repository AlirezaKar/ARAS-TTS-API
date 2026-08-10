from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from app.services.tts.base import ensure_parent, finalize_format


class StubEngine:
    """
    Offline stub that writes a short beep WAV.
    Used only when no real TTS engine is available (dev/CI smoke tests).
    """

    name = "stub"

    def is_available(self) -> tuple[bool, str]:
        return True, "offline beep stub (no real speech)"

    def synthesize(self, text: str, out_path: Path, fmt: str) -> Path:
        ensure_parent(out_path)
        wav_path = out_path.with_suffix(".wav")
        rate = 22050
        duration = min(3.0, max(0.4, len(text) / 40.0))
        frequency = 440.0
        n_samples = int(rate * duration)
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            frames = bytearray()
            for i in range(n_samples):
                # simple envelope so it is audible
                env = 0.3 if i < n_samples * 0.9 else 0.3 * (1 - (i / n_samples))
                value = int(env * 32767 * math.sin(2 * math.pi * frequency * (i / rate)))
                frames += struct.pack("<h", value)
            wf.writeframes(frames)

        try:
            return finalize_format(wav_path, fmt)
        except RuntimeError:
            # mp3 conversion may fail without ffmpeg — return wav
            return wav_path
