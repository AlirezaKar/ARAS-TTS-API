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
    app_port: int = 8000
    debug: bool = False

    root_dir: Path = ROOT_DIR
    output_dir: Path = ROOT_DIR / "output"
    audio_dir: Path = ROOT_DIR / "output" / "audio"
    jobs_dir: Path = ROOT_DIR / "output" / "jobs"
    uploads_dir: Path = ROOT_DIR / "output" / "uploads"
    models_dir: Path = ROOT_DIR / "models"
    lexicon_path: Path = ROOT_DIR / "fine_tuning" / "lexicon.json"
    phone_map_path: Path = ROOT_DIR / "fine_tuning" / "phone_chat_map.json"

    # Piper
    piper_model_path: Path = ROOT_DIR / "models" / "fa_IR-amir-medium.onnx"
    piper_lca_model_path: Path = ROOT_DIR / "models" / "fa_IR-mana-medium.onnx"

    # Cloud / bots
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    # Default model: v2 alias or full id (v1=flash_v2_5, v2=multilingual_v2, v3=eleven_v3)
    elevenlabs_model_id: str = "v2"

    bale_bot_token: str = ""
    bale_api_base: str = "https://tapi.bale.ai"

    telegram_bot_token: str = ""
    telegram_api_base: str = "https://api.telegram.org"

    whatsapp_cloud_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_api_base: str = "https://graph.facebook.com/v19.0"

    # Playwright session dirs
    # Use installed Edge (channel) so Iran geo-blocks on Playwright CDN are avoided.
    # Values: msedge | chrome | chromium (chromium needs playwright install)
    playwright_channel: str = "msedge"
    playwright_whatsapp_user_data: Path = ROOT_DIR / "output" / "sessions" / "whatsapp"
    playwright_telegram_user_data: Path = ROOT_DIR / "output" / "sessions" / "telegram"
    playwright_bale_user_data: Path = ROOT_DIR / "output" / "sessions" / "bale"
    playwright_headless: bool = False
    # When true, TTS still runs but social send is skipped (useful for local audio tests)
    skip_messaging: bool = False

    default_audio_format: str = "mp3"
    allowed_extensions: frozenset[str] = frozenset({".txt", ".pdf", ".docx"})

    def ensure_dirs(self) -> None:
        for path in (
            self.output_dir,
            self.audio_dir,
            self.jobs_dir,
            self.uploads_dir,
            self.models_dir,
            self.playwright_whatsapp_user_data,
            self.playwright_telegram_user_data,
            self.playwright_bale_user_data,
            self.lexicon_path.parent,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s


settings = get_settings()
