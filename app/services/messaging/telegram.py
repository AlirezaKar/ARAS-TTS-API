from __future__ import annotations

from pathlib import Path

import httpx

from app.core.config import settings
from app.schemas import Platform, SendResult
from app.services.messaging.phone_map import resolve_chat_id


class TelegramMessenger:
    platform = Platform.telegram

    def send_audio(self, phone_number: str, audio_path: Path, caption: str = "") -> SendResult:
        if not settings.telegram_bot_token:
            from app.services.messaging.playwright_fallback import PlaywrightMessenger

            return PlaywrightMessenger(Platform.telegram).send_audio(
                phone_number, audio_path, caption
            )

        chat_id = resolve_chat_id(phone_number, "telegram")
        if not chat_id:
            from app.services.messaging.playwright_fallback import PlaywrightMessenger

            pw = PlaywrightMessenger(Platform.telegram).send_audio(
                phone_number, audio_path, caption
            )
            if pw.success:
                return pw
            return SendResult(
                platform=Platform.telegram,
                success=False,
                detail=(
                    "No Telegram chat_id mapped for this phone and Playwright fallback failed. "
                    f"Register in fine_tuning/phone_chat_map.json. Playwright: {pw.detail}"
                ),
                method="bot",
            )

        base = f"{settings.telegram_api_base}/bot{settings.telegram_bot_token}"
        try:
            with httpx.Client(timeout=60.0) as client:
                with audio_path.open("rb") as f:
                    resp = client.post(
                        f"{base}/sendDocument",
                        data={"chat_id": chat_id, "caption": caption or "TTS audio"},
                        files={"document": (audio_path.name, f)},
                    )
                if resp.status_code >= 400:
                    with audio_path.open("rb") as f2:
                        resp = client.post(
                            f"{base}/sendVoice",
                            data={"chat_id": chat_id, "caption": caption or "TTS audio"},
                            files={"voice": (audio_path.name, f2)},
                        )
                resp.raise_for_status()
            return SendResult(
                platform=Platform.telegram,
                success=True,
                detail=f"Sent via Telegram Bot API to chat_id={chat_id}",
                method="bot",
            )
        except Exception as exc:  # noqa: BLE001
            from app.services.messaging.playwright_fallback import PlaywrightMessenger

            pw = PlaywrightMessenger(Platform.telegram).send_audio(
                phone_number, audio_path, caption
            )
            if pw.success:
                return pw
            return SendResult(
                platform=Platform.telegram,
                success=False,
                detail=f"Telegram bot failed: {exc}; Playwright: {pw.detail}",
                method="bot",
            )
