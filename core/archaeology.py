"""Археология: серверная часть.

Правила (сколько осколков складываются в карту, размер клада, тексты) —
общие для обоих стеков и живут в `engine/gathering.py`. Здесь остаётся
работа с БД и координатами конкретного мира.
"""
import random

from sqlalchemy import select

from engine import gathering as G
from core.models import Character, Cell, Location


async def find_relic_fragment(session, character: Character) -> dict:
    """Найти фрагмент древней скрижали."""
    found, formed_map = G.fragment_progress(character.relic_fragments)
    character.relic_fragments = found

    coords = None
    if formed_map:
        # Координаты тайника выбираются по реальному миру сервера.
        loc_id = random.randint(1, 4)
        target_x = random.randint(2, 7)
        target_y = random.randint(2, 7)
        character.treasure_map_coord = f"loc:{loc_id}:x:{target_x}:y:{target_y}"
        coords = (target_x, target_y)

    await session.flush()
    return {
        "ok": True,
        "fragments": character.relic_fragments,
        "formed_map": formed_map,
        "desc": G.fragment_text(found, formed_map, coords),
    }


async def dig_treasure_at_cell(session, character: Character, cell: Cell) -> dict:
    """Раскопать клад по координатам карты сокровищ."""
    from engine.currency import add_currency
    target_str = getattr(character, "treasure_map_coord", None)
    if not target_str:
        return {"ok": False, "reason": "У тебя нет собранной карты сокровищ!"}

    expected = f"loc:{cell.location_id}:x:{cell.x}:y:{cell.y}"
    if target_str != expected:
        return {"ok": False, "reason": "Здесь ничего не зарыто. Сверься с координатами карты!"}

    character.treasure_map_coord = None
    gold_reward = random.randint(*G.TREASURE_GOLD)
    add_currency(character, bronze=gold_reward)
    character.soul_ash = (character.soul_ash or 0) + G.TREASURE_ASH
    character.experience = (character.experience or 0) + G.TREASURE_EXP

    await session.flush()
    return {
        "ok": True,
        "title": "🏆 ДРЕВНИЙ КЛАД РАСКОПАН!",
        "desc": (f"Под слоем земли лежал кованый сундук предков!\n\n"
                 f"Добыча: +{gold_reward}🟤 | +{G.TREASURE_ASH} 🕯 Праха предков "
                 f"| +{G.TREASURE_EXP}⭐ опыта!"),
    }
