"""Итоговые характеристики персонажа с учётом экипировки.

Экипированные вещи — это уникальные экземпляры (`ItemInstance`) со своими
статами, поэтому бонусы нельзя брать из шаблона предмета. Здесь всё
собирается в одном месте, чтобы бой, профиль и админка считали одинаково.
"""
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core import durability
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
        inst = inv.instance if inv.instance_id else None
        if inst is not None and durability.is_gear(inst, inv.item) and durability.broken(inst):
            continue                       # сломано — слот не усиливает
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
    """Полная сводка: база + экипировка + фракционные бонусы. Используется боем и профилем."""
    gear = await equipped_items(session, character.id)
    bonus = sum_bonuses(gear)

    from core import factions as core_factions
    my_f = core_factions.allegiance(character)
    decree_b = await core_factions.active_decree_bonuses(session, my_f)
    outpost_b = await core_factions.faction_outpost_bonuses(session, my_f)

    from core import subclasses as core_subs
    from core import talents as core_talents
    from core import titles as core_titles

    sub_b = core_subs.subclass_bonuses(character)
    tal_b = core_talents.talent_bonuses(character)
    tit_b = core_titles.title_bonus(character)

    damage_mult = decree_b.get("damage_mult", 1.0) * (1.0 + outpost_b.get("damage_pct", 0) / 100.0) * sub_b.get("damage_mult", 1.0)
    defense_mult = decree_b.get("defense_mult", 1.0) * (1.0 + outpost_b.get("defense_pct", 0) / 100.0) * sub_b.get("defense_mult", 1.0)
    exp_mult = decree_b.get("exp_mult", 1.0) * (1.0 + outpost_b.get("exp_pct", 0) / 100.0)
    gold_mult = decree_b.get("gold_mult", 1.0) * (1.0 + outpost_b.get("gold_pct", 0) / 100.0)

    stats = {
        "strength": (character.strength or 0) + bonus["strength"],
        "agility": (character.agility or 0) + bonus["agility"],
        "intelligence": (character.intelligence or 0) + bonus["intelligence"],
        "endurance": (character.endurance or 0) + bonus["endurance"],
        "luck": (character.luck or 0) + bonus["luck"] + tal_b.get("luck", 0) + tit_b.get("luck", 0),
        "max_hp": (character.max_hp or 0) + bonus["max_hp"] + tit_b.get("hp", 0),
        "max_mp": (character.max_mp or 0) + bonus["max_mp"],
        "damage": bonus["damage"] + tal_b.get("damage", 0) + tit_b.get("damage", 0),
        "defense": bonus["defense"] + tal_b.get("defense", 0) + tit_b.get("defense", 0),
        "damage_mult": damage_mult,
        "defense_mult": defense_mult,
        "exp_mult": exp_mult,
        "gold_mult": gold_mult,
        "vampirism_pct": sub_b.get("vampirism_pct", 0),
        "gear": gear,
        "bonus": bonus,
    }
    return stats


def attack_power(stats: dict, character) -> int:
    """Базовый урон: сила/интеллект по классу + урон оружия + фракционные бонусы."""
    # Магические классы бьют интеллектом, если он заметно выше силы
    scaling = max(stats["strength"], int(stats["intelligence"] * 0.9))
    base = max(1, scaling + stats["damage"])
    mult = stats.get("damage_mult", 1.0)
    return max(1, int(base * mult))


def damage_reduction(stats: dict) -> int:
    """Сколько урона срезает броня и выносливость."""
    base = stats["defense"] + stats["endurance"] // 5
    mult = stats.get("defense_mult", 1.0)
    return int(base * mult)


def simulate_gear_loadout(character, hypothetical_items: list) -> dict:
    """Симулятор экипировки: предпросмотр параметров до покупки на аукционе."""
    bonus = sum_bonuses(hypothetical_items)
    from engine.stats import calculate_gear_score

    simulated_stats = {
        "strength": (character.strength or 10) + bonus["strength"],
        "agility": (character.agility or 10) + bonus["agility"],
        "intelligence": (character.intelligence or 10) + bonus["intelligence"],
        "endurance": (character.endurance or 10) + bonus["endurance"],
        "luck": (character.luck or 10) + bonus["luck"],
        "max_hp": (character.max_hp or 100) + bonus["max_hp"],
        "max_mp": (character.max_mp or 50) + bonus["max_mp"],
        "damage": bonus["damage"],
        "defense": bonus["defense"],
    }
    return {
        "stats": simulated_stats,
        "attack_power": max(1, simulated_stats["strength"] + simulated_stats["damage"]),
        "damage_reduction": simulated_stats["defense"] + simulated_stats["endurance"] // 5,
    }

