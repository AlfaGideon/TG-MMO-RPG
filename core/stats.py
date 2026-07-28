"""Итоговые характеристики персонажа с учётом экипировки.

Экипированные вещи — это уникальные экземпляры (`ItemInstance`) со своими
статами, поэтому бонусы нельзя брать из шаблона предмета. Здесь всё
собирается в одном месте, чтобы бой, профиль и админка считали одинаково.
"""
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.models import InventoryItem, ItemInstance

STAT_KEYS = ("strength", "agility", "intelligence", "endurance", "luck")

BONUS_TO_STAT = {
    "bonus_strength": "strength",
    "bonus_agility": "agility",
    "bonus_intelligence": "intelligence",
    "bonus_endurance": "endurance",
    "bonus_luck": "luck",
    "bonus_hp": "max_hp",
    "bonus_mp": "max_mp",
}


async def equipped_items(session, character_id: int):
    """Все надетые вещи вместе с их уникальными экземплярами."""
    result = await session.execute(
        select(InventoryItem)
        .where(InventoryItem.character_id == character_id)
        .where(InventoryItem.is_equipped == True)  # noqa: E712
        .options(
            selectinload(InventoryItem.item),
            selectinload(InventoryItem.instance).selectinload(ItemInstance.item),
        )
    )
    return result.scalars().all()


def sum_bonuses(inv_items) -> dict:
    """Складывает бонусы всех переданных вещей."""
    total = {
        "strength": 0, "agility": 0, "intelligence": 0, "endurance": 0,
        "luck": 0, "max_hp": 0, "max_mp": 0, "damage": 0, "defense": 0,
    }
    for inv in inv_items:
        bonuses = inv.bonuses()
        for field, value in bonuses.items():
            if not value:
                continue
            if field == "bonus_damage":
                total["damage"] += value
            elif field == "bonus_defense":
                total["defense"] += value
            else:
                key = BONUS_TO_STAT.get(field)
                if key:
                    total[key] += value
    return total


async def combat_stats(session, character) -> dict:
    """Полная сводка: база + экипировка. Используется боем и профилем."""
    gear = await equipped_items(session, character.id)
    bonus = sum_bonuses(gear)

    stats = {
        "strength": character.strength + bonus["strength"],
        "agility": character.agility + bonus["agility"],
        "intelligence": character.intelligence + bonus["intelligence"],
        "endurance": character.endurance + bonus["endurance"],
        "luck": character.luck + bonus["luck"],
        "max_hp": character.max_hp + bonus["max_hp"],
        "max_mp": character.max_mp + bonus["max_mp"],
        "damage": bonus["damage"],
        "defense": bonus["defense"],
        "gear": gear,
        "bonus": bonus,
    }
    return stats


def attack_power(stats: dict, character) -> int:
    """Базовый урон: сила/интеллект по классу + урон оружия."""
    # Магические классы бьют интеллектом, если он заметно выше силы
    scaling = max(stats["strength"], int(stats["intelligence"] * 0.9))
    return max(1, scaling + stats["damage"])


def damage_reduction(stats: dict) -> int:
    """Сколько урона срезает броня и выносливость."""
    return stats["defense"] + stats["endurance"] // 5
