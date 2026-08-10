from __future__ import annotations

from pathlib import Path

from app.services.tts.base import ensure_parent, finalize_format


class PersianTTSMRJEngine:
    """Local persian-tts-mrj package when installed."""

    name = "persian_tts_mrj"

    def is_available(self) -> tuple[bool, str]:
        try:
            import persian_tts_mrj  # noqa: F401
        except ImportError:
            try:
                import persian_tts  # noqa: F401
            except ImportError:
                return False, "persian-tts-mrj (or persian_tts) not installed"
        return True, "package available"

    def synthesize(self, text: str, out_path: Path, fmt: str) -> Path:
        ok, detail = self.is_available()
        if not ok:
            raise RuntimeError(detail)

        ensure_parent(out_path)
        wav_path = out_path.with_suffix(".wav")

        # Try known package entrypoints
        try:
            from persian_tts_mrj import TTS as MRJTTS  # type: ignore

            tts = MRJTTS()
            audio = tts.tts(text)
            self._write_audio(audio, wav_path)
        except Exception:
            try:
                import persian_tts_mrj as mrj  # type: ignore

                if hasattr(mrj, "synthesize"):
                    mrj.synthesize(text, str(wav_path))
                elif hasattr(mrj, "tts"):
                    audio = mrj.tts(text)
                    self._write_audio(audio, wav_path)
                else:
                    raise RuntimeError("persian_tts_mrj has no known synthesize API")
            except Exception as exc:  # noqa: BLE001
                # Last resort: edge-tts style fallback not used; fail clearly
                raise RuntimeError(f"persian-tts-mrj synthesis failed: {exc}") from exc

        return finalize_format(wav_path, fmt)

    @staticmethod
    def _write_audio(audio: object, wav_path: Path) -> None:
        import numpy as np
        import wave

        if isinstance(audio, (bytes, bytearray)):
            wav_path.write_bytes(audio)
            return

        arr = np.asarray(audio)
        if arr.dtype != np.int16:
            # assume float -1..1
            arr = (arr * 32767).astype(np.int16)
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            wf.writeframes(arr.tobytes())
