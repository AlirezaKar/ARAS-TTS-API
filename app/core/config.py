from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Persian TTS-API"
    app_host: str = "0.0.0.0"
    app_port: int = 5004
    debug: bool = False

    root_dir: Path = ROOT_DIR
    output_dir: Path = ROOT_DIR / "output"
    audio_dir: Path = ROOT_DIR / "output" / "audio"
    jobs_dir: Path = ROOT_DIR / "output" / "jobs"
    uploads_dir: Path = ROOT_DIR / "output" / "uploads"
    models_dir: Path = ROOT_DIR / "models"
    lexicon_path: Path = ROOT_DIR / "fine_tuning" / "lexicon.json"
    pronunciation_db_path: Path = ROOT_DIR / "fine_tuning" / "pronunciation.db"

    # Direct Gemini TTS (engine=gemini) — independent of Apps Script
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-preview-tts"
    gemini_voice: str = "Kore"
    gemini_prompt: str = "Say the following clearly in Persian."
    # developer = AI Studio generateContent (API key, recommended free tier)
    # cloud = texttospeech.googleapis.com Gemini-TTS (often needs GCP project)
    gemini_tts_backend: str = "developer"
    gemini_language_code: str = "fa-IR"
    google_cloud_project: str = ""

    # Google Studio via Apps Script (engine=google_studio) — unchanged path
    google_apps_script_url: str = ""

    default_audio_format: str = "wav"
    allowed_extensions: frozenset[str] = frozenset({".txt", ".pdf", ".docx"})

    def ensure_dirs(self) -> None:
        for path in (
            self.output_dir,
            self.audio_dir,
            self.jobs_dir,
            self.uploads_dir,
            self.models_dir,
            self.lexicon_path.parent,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s


settings = get_settings()
