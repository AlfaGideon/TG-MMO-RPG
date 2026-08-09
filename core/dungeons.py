"""
Dungeon portal lifecycle helpers, shared by the admin panel and the bot.

A portal opened on the world map stays open for new entries for at most
PORTAL_MAX_LIFETIME (2 hours), or until an admin closes it manually.
Closing a portal only blocks *new* entries — anyone with an already-active
DungeonRun keeps playing (their run references the template by id directly,
independent of the world cell), until they die or leave voluntarily.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from core.models import Cell, DungeonTemplate

PORTAL_MAX_LIFETIME = timedelta(hours=2)


def _now():
    # aware-время: колонки timestamptz, на Postgres datetime.utcnow() ломал
    # сравнения («naive vs aware»), порталы не закрывались никогда.
    return datetime.now(timezone.utc)


def _aware(dt):
    """SQLite возвращает naive, Postgres — aware; приводим к aware."""
    return dt if (dt is None or dt.tzinfo) else dt.replace(tzinfo=timezone.utc)


async def close_portal(session, template: DungeonTemplate):
    """Blocks new entries into this template's dungeon: keeps the template
    row itself (so anyone already inside keeps generating floors normally),
    but removes the world-map cell link so the entry button disappears."""
    if template.portal_closed_at is None:
        template.portal_closed_at = _now()

    result = await session.execute(
        select(Cell).where(Cell.dungeon_template_id == template.id)
    )
    for cell in result.scalars().all():
        cell.dungeon_template_id = None
        if cell.tile_type == "portal":
            cell.tile_type = "road"


def is_portal_open(template: DungeonTemplate) -> bool:
    """Pure check: is this template currently accepting new entries?"""
    if template is None or not template.is_active:
        return False
    if template.portal_closed_at is not None:
        return False
    if template.portal_opened_at is not None \
            and _now() - _aware(template.portal_opened_at) > PORTAL_MAX_LIFETIME:
        return False
    return True


DUNGEON_AFFIXES = {
    "ash": {
        "name": "🌋 Густой пепел",
        "desc": "Радиус обзора ограничен 1 клеткой, но качество найденных предметов увеличено на +25%.",
        "loot_quality_mult": 1.25,
    },
    "bloodlust": {
        "name": "🩸 Жажда крови",
        "desc": "Обычная регенерация отключена, но каждая успешная атака восстанавливает 20% нанесённого урона.",
        "vampirism_pct": 20,
    },
    "gold_vein": {
        "name": "💰 Золотая жила",
        "desc": "Враги и сундуки приносят +100% золота, но монстры бьют чистым уроном.",
        "gold_mult": 2.0,
    },
    "elemental_surge": {
        "name": "⚡ Аномалия стихий",
        "desc": "Урон всех элементальных комбо-реакций удвоен (+100%).",
        "reaction_mult": 2.0,
    },
}


def roll_affixes(count: int = 1) -> list[str]:
    """Случайные мутаторы для нового забега в подземелье."""
    import random
    keys = list(DUNGEON_AFFIXES.keys())
    return random.sample(keys, min(count, len(keys)))


async def use_corrupted_altar(session, character, run, altar_type: str) -> dict:
    """Использование осквернённого алтаря на этаже подземелья."""
    if altar_type == "abyssal":
        run.altar_boon = "abyssal_strength"
        return {
            "ok": True,
            "title": "🖤 Дар Бездны",
            "desc": "Ты вдохнул тёмный фиолетовый туман. Твой урон увеличен на +40% до конца забега, но сердце бьётся слабее.",
        }
    elif altar_type == "blood":
        from engine.currency import deduct_currency
        deduct_currency(character, 150)
        character.current_hp = character.max_hp
        character.current_mp = character.max_mp
        return {
            "ok": True,
            "title": "🩸 Кровавая сделка",
            "desc": "Кровь на камне зашипела. Твои раны мгновенно затянулись, а силы восстановились! (−150🟤)",
        }
    elif altar_type == "insight":
        # Открыть все клетки на текущем этаже
        from core.models import DungeonCell
        result = await session.execute(
            select(DungeonCell).where(DungeonCell.run_id == run.id)
        )
        for c in result.scalars().all():
            c.is_visited = True
        return {
            "ok": True,
            "title": "👁 Око Прозрения",
            "desc": "Вспышка разума осветила весь лабиринт! Вся карта этажа теперь открыта перед твоим взором.",
        }
    return {"ok": False, "reason": "Неизвестный алтарь."}

