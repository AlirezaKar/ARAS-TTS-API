from __future__ import annotations

from app.schemas import Accuracy, EngineInfo
from app.services.tts.edge_tts_engine import EdgeTTSEngine
from app.services.tts.elevenlabs_engine import ElevenLabsEngine
from app.services.tts.persian_tts_mrj import PersianTTSMRJEngine
from app.services.tts.piper_engine import PiperEngine
from app.services.tts.piper_lca_engine import PiperLCAEngine
from app.services.tts.stub_engine import StubEngine
from app.services.tts.ttskit_engine import TTSKitEngine

# Accuracy tier → preferred engine order (first available wins at runtime if needed)
ACCURACY_ENGINE_MAP: dict[Accuracy, str] = {
    Accuracy.fast: "persian_tts_mrj",
    Accuracy.balanced: "piper_lca",
    Accuracy.high: "ttskit",
    Accuracy.premium: "elevenlabs",
}

# Fallbacks when preferred engine is unavailable
FALLBACKS: dict[Accuracy, list[str]] = {
    Accuracy.fast: ["persian_tts_mrj", "piper", "piper_lca", "edge_tts", "stub"],
    Accuracy.balanced: ["piper_lca", "piper", "persian_tts_mrj", "edge_tts", "stub"],
    Accuracy.high: ["ttskit", "piper_lca", "elevenlabs", "piper", "edge_tts", "stub"],
    Accuracy.premium: ["elevenlabs", "ttskit", "piper_lca", "edge_tts", "stub"],
}


def _all_engines() -> dict[str, object]:
    return {
        "piper": PiperEngine(),
        "piper_lca": PiperLCAEngine(),
        "persian_tts_mrj": PersianTTSMRJEngine(),
        "ttskit": TTSKitEngine(),
        "elevenlabs": ElevenLabsEngine(),
        "edge_tts": EdgeTTSEngine(),
        "stub": StubEngine(),
    }


def list_engines() -> list[EngineInfo]:
    engines = _all_engines()
    infos: list[EngineInfo] = []
    for accuracy, eng_name in ACCURACY_ENGINE_MAP.items():
        eng = engines[eng_name]
        available, detail = eng.is_available()  # type: ignore[attr-defined]
        infos.append(
            EngineInfo(
                accuracy=accuracy,
                engine=eng_name,
                available=available,
                detail=detail,
            )
        )
    # Also list other installed engines
    mapped = set(ACCURACY_ENGINE_MAP.values())
    for name, eng in engines.items():
        if name in mapped:
            continue
        available, detail = eng.is_available()  # type: ignore[attr-defined]
        infos.append(
            EngineInfo(
                accuracy=Accuracy.fast,
                engine=name,
                available=available,
                detail=detail,
            )
        )
    return infos


def get_engine_for_accuracy(
    accuracy: Accuracy,
    allow_fallback: bool = True,
    *,
    elevenlabs_model: str | None = None,
):
    engines = _all_engines()
    order = FALLBACKS.get(accuracy, [ACCURACY_ENGINE_MAP[accuracy]])
    if not allow_fallback:
        order = [ACCURACY_ENGINE_MAP[accuracy]]

    errors: list[str] = []
    for name in order:
        if name == "elevenlabs":
            eng = ElevenLabsEngine(model_id=elevenlabs_model)
        else:
            eng = engines.get(name)
        if eng is None:
            continue
        ok, detail = eng.is_available()  # type: ignore[attr-defined]
        if ok:
            return eng, name
        errors.append(f"{name}: {detail}")

    raise RuntimeError(
        f"No TTS engine available for accuracy='{accuracy.value}'. "
        + "; ".join(errors)
    )
