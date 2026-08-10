from __future__ import annotations

from pathlib import Path

from app.schemas import Platform, SendResult
from app.services.messaging.bale import BaleMessenger
from app.services.messaging.telegram import TelegramMessenger
from app.services.messaging.whatsapp import WhatsAppMessenger


def get_messenger(platform: Platform):
    if platform == Platform.bale:
        return BaleMessenger()
    if platform == Platform.telegram:
        return TelegramMessenger()
    if platform == Platform.whatsapp:
        return WhatsAppMessenger()
    raise ValueError(f"Unknown platform: {platform}")


def send_voice(
    platform: Platform,
    phone_number: str,
    audio_path: Path,
    caption: str = "",
) -> SendResult:
    messenger = get_messenger(platform)
    return messenger.send_audio(phone_number, audio_path, caption)
