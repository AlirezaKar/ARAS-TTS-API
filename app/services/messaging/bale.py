from __future__ import annotations

from pathlib import Path

import httpx

from app.core.config import settings
from app.schemas import Platform, SendResult
from app.services.messaging.phone_map import resolve_chat_id


class BaleMessenger:
    platform = Platform.bale

    def send_audio(self, phone_number: str, audio_path: Path, caption: str = "") -> SendResult:
        if not settings.bale_bot_token:
            # Try Playwright fallback
            from app.services.messaging.playwright_fallback import PlaywrightMessenger

            return PlaywrightMessenger(Platform.bale).send_audio(
                phone_number, audio_path, caption
            )

        chat_id = resolve_chat_id(phone_number, "bale")
        if not chat_id:
            # Fallback to Playwright for phone-number send
            from app.services.messaging.playwright_fallback import PlaywrightMessenger

            pw = PlaywrightMessenger(Platform.bale).send_audio(
                phone_number, audio_path, caption
            )
            if pw.success:
                return pw
            return SendResult(
                platform=Platform.bale,
                success=False,
                detail=(
                    "No Bale chat_id mapped for this phone and Playwright fallback failed. "
                    f"Register phone in fine_tuning/phone_chat_map.json. Playwright: {pw.detail}"
                ),
                method="bot",
            )

        url = f"{settings.bale_api_base}/bot{settings.bale_bot_token}/sendDocument"
        try:
            with httpx.Client(timeout=60.0) as client:
                with audio_path.open("rb") as f:
                    resp = client.post(
                        url,
                        data={"chat_id": chat_id, "caption": caption or "TTS audio"},
                        files={"document": (audio_path.name, f)},
                    )
                if resp.status_code >= 400:
                    # try sendAudio / sendVoice style
                    url2 = f"{settings.bale_api_base}/bot{settings.bale_bot_token}/sendAudio"
                    with audio_path.open("rb") as f2:
                        resp = client.post(
                            url2,
                            data={"chat_id": chat_id, "caption": caption or "TTS audio"},
                            files={"audio": (audio_path.name, f2)},
                        )
                resp.raise_for_status()
            return SendResult(
                platform=Platform.bale,
                success=True,
                detail=f"Sent via Bale Bot API to chat_id={chat_id}",
                method="bot",
            )
        except Exception as exc:  # noqa: BLE001
            from app.services.messaging.playwright_fallback import PlaywrightMessenger

            pw = PlaywrightMessenger(Platform.bale).send_audio(
                phone_number, audio_path, caption
            )
            if pw.success:
                return pw
            return SendResult(
                platform=Platform.bale,
                success=False,
                detail=f"Bale bot failed: {exc}; Playwright: {pw.detail}",
                method="bot",
            )
