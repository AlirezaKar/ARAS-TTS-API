from __future__ import annotations

from pathlib import Path

from app.services.tts.base import ensure_parent, finalize_format


class TTSKitEngine:
    """
    TTSKit multi-engine wrapper.
    Uses TTSKit if installed; otherwise reports unavailable.
    """

    name = "ttskit"

    def is_available(self) -> tuple[bool, str]:
        try:
            import ttskit  # noqa: F401
        except ImportError:
            try:
                from ttskit import TTS  # noqa: F401
            except ImportError:
                return (
                    False,
                    "TTSKit not installed "
                    "(pip install git+https://github.com/dibbed/TTSKit-multi-engine-tts.git)",
                )
        return True, "TTSKit package available"

    def synthesize(self, text: str, out_path: Path, fmt: str) -> Path:
        ok, detail = self.is_available()
        if not ok:
            raise RuntimeError(detail)

        ensure_parent(out_path)
        wav_path = out_path.with_suffix(".wav")

        try:
            from ttskit import TTS

            tts = TTS()
            # Common patterns across versions
            if hasattr(tts, "tts_to_file"):
                tts.tts_to_file(text=text, file_path=str(wav_path))
            elif hasattr(tts, "synthesize"):
                result = tts.synthesize(text)
                if isinstance(result, (str, Path)):
                    Path(result).replace(wav_path)
                else:
                    wav_path.write_bytes(result)
            else:
                raise RuntimeError("TTSKit TTS object has no synthesize/tts_to_file")
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"TTSKit synthesis failed: {exc}") from exc

        return finalize_format(wav_path, fmt)
