"""Разбор снаряжения на ремесленные материалы.

Таблица выхода — **единственный источник правды** для обоих стеков:
`core/salvage.py` берёт её отсюда. Раньше числа (сколько лома даёт
редкая вещь, когда падает магическая пыль) существовали только на
сервере и при переносе легко раздвоились бы.

Функция `yield_for` работает с обычными значениями (редкость строкой и
уровень заточки), поэтому её зовут оба стека: серверу редкость приходит
из `ItemInstance`, движку — из шаблона `engine/data.ITEMS`.
"""

# Сколько лома даёт вещь каждой редкости.
SCRAP_BY_RARITY = {
    "common": 2,
    "uncommon": 4,
    "rare": 8,
    "epic": 15,
    "legendary": 30,
}
SCRAP_PER_UPGRADE = 3       # прибавка за каждый уровень заточки
BARS_PER_TWO_UPGRADES = 2   # заточка +2 даёт один стальной слиток
DUST_RARITIES = ("rare", "epic", "legendary")   # с них падает магическая пыль

MATERIAL_NAMES = {
    "iron_scrap": "🔩 Ржавый лом",
    "steel_bars": "⛓ Стальной слиток",
    "magic_dust": "✨ Магическая пыль",
}


def _rarity_key(rarity) -> str:
    """Редкость строкой: у сервера это Enum, у движка — обычная строка."""
    value = getattr(rarity, "value", rarity)
    return str(value or "common").lower()


def yield_for(rarity, upgrade_level: int = 0) -> dict:
    """Что получится при разборе вещи такой редкости и заточки."""
    key = _rarity_key(rarity)
    upgrade_level = int(upgrade_level or 0)

    scrap = SCRAP_BY_RARITY.get(key, SCRAP_BY_RARITY["common"])
    scrap += upgrade_level * SCRAP_PER_UPGRADE
    return {
        "iron_scrap": scrap,
        "steel_bars": max(0, upgrade_level // BARS_PER_TWO_UPGRADES),
        "magic_dust": 1 if key in DUST_RARITIES else 0,
    }


def yield_text(materials: dict) -> str:
    """Строка выхода материалов — одинаковая в обоих стеках."""
    parts = [f"{MATERIAL_NAMES[key]} ×{count}"
             for key, count in materials.items() if count]
    return "\n".join(parts) if parts else "ничего полезного"
