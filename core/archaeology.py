"""Археология и сбор древних фрагментов скрижалей."""
import random
from sqlalchemy import select
from core.models import Character, Cell, Location


async def find_relic_fragment(session, character: Character) -> dict:
    """Найти фрагмент древней скрижали."""
    frags = (character.relic_fragments or 0) + 1
    formed_map = False

    if frags >= 5:
        character.relic_fragments = 0
        # Выбираем случайную локацию и координаты для карты сокровищ
        loc_id = random.randint(1, 4)
        target_x = random.randint(2, 7)
        target_y = random.randint(2, 7)
        character.treasure_map_coord = f"loc:{loc_id}:x:{target_x}:y:{target_y}"
        formed_map = True
        msg = f"📜 <b>Все 5 фрагментов собраны!</b>\n\nТы восстановил древнюю карту сокровищ! Тайник скрыт на координатах [{target_x},{target_y}]!"
    else:
        character.relic_fragments = frags
        msg = f"🔍 <b>Найден фрагмент скрижали ({frags}/5)!</b>"

    await session.flush()
    return {
        "ok": True,
        "fragments": character.relic_fragments,
        "formed_map": formed_map,
        "desc": msg,
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
    gold_reward = random.randint(300, 700)
    add_currency(character, bronze=gold_reward)
    character.soul_ash = (character.soul_ash or 0) + 30
    character.experience = (character.experience or 0) + 200

    await session.flush()
    return {
        "ok": True,
        "title": "🏆 ДРЕВНИЙ КЛАД РАСКОПАН!",
        "desc": f"Под слоем земли лежал кованый сундук предков!\n\nДобыча: +{gold_reward}🟤 | +30 🕯 Праха предков | +200⭐ опыта!",
    }
