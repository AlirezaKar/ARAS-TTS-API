from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.schemas import Platform, SendResult


class Messenger(Protocol):
    platform: Platform

    def send_audio(self, phone_number: str, audio_path: Path, caption: str = "") -> SendResult:
        ...


def normalize_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone.strip() if ch.isdigit() or ch == "+")
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if digits.startswith("0") and not digits.startswith("00"):
        # Assume Iran local
        digits = "+98" + digits[1:]
    if digits.isdigit() and digits.startswith("98"):
        digits = "+" + digits
    if digits.isdigit() and len(digits) == 10:
        digits = "+98" + digits
    return digits
