from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.services.tts.base import ensure_parent, finalize_format
from app.services.tts.piper_engine import PiperEngine


class PiperLCAEngine:
    """
    Piper with Mana/LCA-oriented Persian model.
    Uses Mana Persian Piper checkpoint when present; falls back to documenting
    LCA phonemizer integration when the forked binary is not installed.
    """

    name = "piper_lca"

    def __init__(self, model_path: Path | None = None) -> None:
        self.model_path = model_path or settings.piper_lca_model_path
        self._fallback = PiperEngine(model_path=self.model_path)

    def is_available(self) -> tuple[bool, str]:
        if self.model_path.exists():
            try:
                import piper  # noqa: F401
            except ImportError:
                return False, "piper-tts package not installed"
            return True, f"Mana/LCA model={self.model_path.name}"

        # Soft-check for optional LCA service
        stock = settings.piper_model_path
        if stock.exists():
            return (
                True,
                f"LCA model missing; will use stock Piper at {stock.name} "
                "(place fa_IR-mana-medium.onnx for balanced accuracy)",
            )
        return (
            False,
            "Neither Mana LCA model nor stock Piper model found in models/",
        )

    def synthesize(self, text: str, out_path: Path, fmt: str) -> Path:
        ok, detail = self.is_available()
        if not ok:
            raise RuntimeError(detail)

        model = self.model_path if self.model_path.exists() else settings.piper_model_path
        engine = PiperEngine(model_path=model)
        # Mild preprocessing hint: keep harakat; normalize whitespace
        cleaned = " ".join(text.split())
        return engine.synthesize(cleaned, out_path, fmt)
