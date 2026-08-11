"""Каталог будущих питомцев и сохранённые концепт-листы.

Игровая механика фамильяров пока остаётся в ``core.familiars``. Этот модуль
даёт админке отдельное место для будущих видов, изображений и черновых
бонусов, не смешивая питомцев с боевыми мобами.
"""
from __future__ import annotations

import json
import re

from core.assets import local_asset_exists


CONCEPT_SHEETS = tuple(
    f"/static/pets/sheets/slime_pet_concepts_{index:02d}.jpg"
    for index in range(1, 8)
)
RARITIES = ("common", "uncommon", "rare", "epic", "legendary")
RARITY_LABELS = {
    "common": "Обычный", "uncommon": "Необычный", "rare": "Редкий",
    "epic": "Эпический", "legendary": "Легендарный",
}


def available_concept_sheets() -> list[str]:
    return [url for url in CONCEPT_SHEETS if local_asset_exists(url)]


def normalize_key(value: str, fallback: str = "pet") -> str:
    """Стабильный ASCII-ish ключ для callback/будущих сохранений."""
    text = (value or "").strip().lower().replace(" ", "_")
    text = re.sub(r"[^a-z0-9а-яё_\-]+", "", text, flags=re.I)
    return text[:64] or fallback


def normalize_bonuses(value: str) -> str:
    """В БД всегда хранится JSON-объект; мусор отклоняется явно."""
    raw = (value or "").strip() or "{}"
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Бонусы должны быть JSON-объектом")
    return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
