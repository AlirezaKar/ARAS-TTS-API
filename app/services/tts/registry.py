from __future__ import annotations

from app.schemas import EngineInfo, EngineVersionInfo
from app.services.tts.gemini_engine import GEMINI_VOICES, GeminiEngine
from app.services.tts.google_studio_engine import GoogleStudioEngine

# Display order for GET /engines and toolbox
ENGINE_ORDER: tuple[str, ...] = (
    "gemini",
    "google_studio",
)

DISPLAY_NAMES: dict[str, str] = {
    "gemini": "Gemini TTS (direct API)",
    "google_studio": "Google Studio (Apps Script)",
}

_ENGINE_ALIASES: dict[str, str] = {
    "apps_script": "google_studio",
    "google": "google_studio",
}


def _normalize_engine(name: str) -> str:
    raw = (name or "").strip().lower()
    return _ENGINE_ALIASES.get(raw, raw)


normalize_engine = _normalize_engine


def _safe_available(eng) -> tuple[bool, str]:
    try:
        return eng.is_available()  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        return False, f"availability check failed: {exc}"


def _version_infos_for(engine: str) -> list[EngineVersionInfo]:
    if engine == "gemini":
        base_ok, base_detail = _safe_available(GeminiEngine())
        return [
            EngineVersionInfo(id=vid, available=base_ok, detail=base_detail)
            for vid in GEMINI_VOICES
        ]
    return []


def list_engines() -> list[EngineInfo]:
    infos: list[EngineInfo] = []
    for name in ENGINE_ORDER:
        try:
            versions = _version_infos_for(name)
            if versions:
                available = any(v.available for v in versions)
                detail = (
                    f"{sum(1 for v in versions if v.available)}/{len(versions)} voices ready"
                    if available
                    else (versions[0].detail if versions else "unavailable")
                )
            else:
                eng = _instantiate(name, None)
                available, detail = _safe_available(eng)
        except Exception as exc:  # noqa: BLE001
            versions = []
            available = False
            detail = f"engine probe failed: {exc}"
        infos.append(
            EngineInfo(
                engine=name,
                display_name=DISPLAY_NAMES.get(name, name),
                available=available,
                detail=detail,
                versions=versions,
            )
        )
    return infos


def _instantiate(engine: str, version: str | None):
    if engine == "gemini":
        return GeminiEngine(voice=version)
    if engine == "google_studio":
        return GoogleStudioEngine()
    raise ValueError(f"Unknown engine '{engine}'. Known: {', '.join(ENGINE_ORDER)}")


def get_engine(engine: str, version: str | None = None):
    """
    Resolve a specific engine (+ optional version). No silent fallbacks.
    Returns (engine_instance, engine_name, resolved_version).
    """
    name = _normalize_engine(engine)
    if name not in ENGINE_ORDER:
        raise ValueError(f"Unknown engine '{engine}'. Known: {', '.join(ENGINE_ORDER)}")

    ver = version.strip() if version and version.strip() else None

    if name == "gemini":
        eng = GeminiEngine(voice=ver)
        ok, detail = eng.is_available()
        if not ok:
            raise RuntimeError(f"Engine '{name}' unavailable: {detail}")
        return eng, name, eng.voice

    if name == "google_studio":
        if ver is not None:
            raise ValueError(
                "Engine 'google_studio' has no versions "
                "(voice/model are configured inside Apps Script Code.gs)"
            )
        eng = GoogleStudioEngine()
        ok, detail = eng.is_available()
        if not ok:
            raise RuntimeError(f"Engine '{name}' unavailable: {detail}")
        return eng, name, None

    raise ValueError(f"Unknown engine '{engine}'. Known: {', '.join(ENGINE_ORDER)}")
