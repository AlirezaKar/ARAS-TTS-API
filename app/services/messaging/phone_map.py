from __future__ import annotations

import json
from pathlib import Path

from app.core.config import settings


def load_phone_map() -> dict[str, dict[str, str]]:
    """
    Structure:
    {
      "+98912...": {"bale": "123", "telegram": "456"}
    }
    """
    path = settings.phone_map_path
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def save_phone_map(data: dict[str, dict[str, str]]) -> None:
    settings.phone_map_path.parent.mkdir(parents=True, exist_ok=True)
    settings.phone_map_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def resolve_chat_id(phone_number: str, platform: str) -> str | None:
    from app.services.messaging.base import normalize_phone

    phone = normalize_phone(phone_number)
    data = load_phone_map()
    entry = data.get(phone) or data.get(phone_number)
    if not entry:
        # also try without plus
        entry = data.get(phone.lstrip("+"))
    if not entry:
        return None
    return entry.get(platform)


def register_chat_id(phone_number: str, platform: str, chat_id: str) -> None:
    from app.services.messaging.base import normalize_phone

    phone = normalize_phone(phone_number)
    data = load_phone_map()
    data.setdefault(phone, {})[platform] = str(chat_id)
    save_phone_map(data)
