from __future__ import annotations

from pathlib import Path

import httpx

from app.core.config import settings
from app.schemas import Platform, SendResult


class WhatsAppMessenger:
    """WhatsApp: Cloud API if configured, else Playwright WhatsApp Web."""

    platform = Platform.whatsapp

    def send_audio(self, phone_number: str, audio_path: Path, caption: str = "") -> SendResult:
        if settings.whatsapp_cloud_token and settings.whatsapp_phone_number_id:
            result = self._send_cloud(phone_number, audio_path, caption)
            if result.success:
                return result
            # fall through to playwright
            from app.services.messaging.playwright_fallback import PlaywrightMessenger

            pw = PlaywrightMessenger(Platform.whatsapp).send_audio(
                phone_number, audio_path, caption
            )
            if pw.success:
                return pw
            return SendResult(
                platform=Platform.whatsapp,
                success=False,
                detail=f"Cloud API failed: {result.detail}; Playwright: {pw.detail}",
                method="cloud_api",
            )

        from app.services.messaging.playwright_fallback import PlaywrightMessenger

        return PlaywrightMessenger(Platform.whatsapp).send_audio(
            phone_number, audio_path, caption
        )

    def _send_cloud(self, phone_number: str, audio_path: Path, caption: str) -> SendResult:
        from app.services.messaging.base import normalize_phone

        phone = normalize_phone(phone_number).lstrip("+")
        base = f"{settings.whatsapp_api_base}/{settings.whatsapp_phone_number_id}"
        headers = {"Authorization": f"Bearer {settings.whatsapp_cloud_token}"}
        try:
            with httpx.Client(timeout=60.0) as client:
                # upload media
                with audio_path.open("rb") as f:
                    up = client.post(
                        f"{base}/media",
                        headers=headers,
                        data={"messaging_product": "whatsapp"},
                        files={"file": (audio_path.name, f, "audio/mpeg")},
                    )
                up.raise_for_status()
                media_id = up.json().get("id")
                payload = {
                    "messaging_product": "whatsapp",
                    "to": phone,
                    "type": "document",
                    "document": {
                        "id": media_id,
                        "caption": caption or "TTS audio",
                        "filename": audio_path.name,
                    },
                }
                resp = client.post(f"{base}/messages", headers=headers, json=payload)
                resp.raise_for_status()
            return SendResult(
                platform=Platform.whatsapp,
                success=True,
                detail=f"Sent via WhatsApp Cloud API to {phone}",
                method="cloud_api",
            )
        except Exception as exc:  # noqa: BLE001
            return SendResult(
                platform=Platform.whatsapp,
                success=False,
                detail=str(exc),
                method="cloud_api",
            )
