"""Каталог будущих питомцев и сохранённые концепт-листы.

Игровая механика фамильяров пока остаётся в ``core.familiars``. Этот модуль
даёт админке отдельное место для будущих видов, изображений и черновых
бонусов, не смешивая питомцев с боевыми мобами.
"""
from __future__ import annotations


from core.assets import local_asset_exists


CONCEPT_SHEETS = tuple(
    f"/static/pets/sheets/slime_pet_concepts_{index:02d}.jpg"
    for index in range(1, 8)
)
# Правила каталога (ключ, редкость, бонусы) с этой партии живут в
# engine/pets.py — одни на серверную админку и браузерную панель
# (IDEAS-100.md № 20). Здесь остаётся то, что есть только на сервере:
# концепт-листы на диске.
from engine.pets import (  # noqa: F401,E402
    FAMILIES,
    FAMILY_LABELS,
    RARITIES,
    RARITY_ICONS,
    RARITY_LABELS,
    describe_bonuses,
    make_template,
    normalize_family,
    normalize_rarity,
    parse_bonuses,
)


def available_concept_sheets() -> list[str]:
    return [url for url in CONCEPT_SHEETS if local_asset_exists(url)]


from engine.pets import normalize_bonuses, normalize_key  # noqa: F401,E402
