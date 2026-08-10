from __future__ import annotations

import asyncio
from pathlib import Path

from app.services.tts.base import ensure_parent, finalize_format


class EdgeTTSEngine:
    """Microsoft Edge neural TTS fallback (supports Persian voices)."""

    name = "edge_tts"
    voice = "fa-IR-DilaraNeural"

    def is_available(self) -> tuple[bool, str]:
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            return False, "edge-tts not installed"
        return True, f"voice={self.voice}"

    def synthesize(self, text: str, out_path: Path, fmt: str) -> Path:
        ok, detail = self.is_available()
        if not ok:
            raise RuntimeError(detail)

        ensure_parent(out_path)
        mp3_path = out_path.with_suffix(".mp3")

        async def _run() -> None:
            import edge_tts

            communicate = edge_tts.Communicate(text, self.voice)
            await communicate.save(str(mp3_path))

        asyncio.run(_run())

        if fmt.lower().lstrip(".") == "mp3":
            return mp3_path

        # convert to wav
        try:
            from pydub import AudioSegment

            wav_path = out_path.with_suffix(".wav")
            AudioSegment.from_mp3(str(mp3_path)).export(str(wav_path), format="wav")
            return wav_path
        except Exception:
            # If conversion fails, return mp3 anyway via finalize
            return finalize_format(mp3_path, "mp3")
