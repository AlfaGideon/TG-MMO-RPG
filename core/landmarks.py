"""Достопримечательности для серверного стека — паритет с engine/landmarks.py.

Часть описаний клеток — не декорация, а объекты с однократной наградой.
Каталог берётся из `engine.landmarks`, поэтому набор диковин и их награды
одинаковы в обоих стеках.

Клетка узнаётся по имени, а «настоящей» считается только первая клетка
такого имени в локации: названия повторяются десятками, иначе диковин
были бы сотни и ценность пропала бы.
"""
import json
import random

from sqlalchemy import select

from engine import landmarks as E
from core.models import Cell

LANDMARKS = E.LANDMARKS
STATS = E.STATS


def of(cell):
    """Описание диковины этой клетки или None (без проверки уникальности)."""
    if cell is None:
        return None
    row = LANDMARKS.get(cell.name)
    if row is None:
        return None
    icon, kind, text = row
    return {"name": cell.name, "icon": icon, "kind": kind, "text": text}


async def keys(session, location_id=None):
    """Клетки настоящих диковин: по одной каждого вида на локацию."""
    q = select(Cell)
    if location_id is not None:
        q = q.where(Cell.location_id == location_id)
    result = await session.execute(q)
    best = {}
    for c in result.scalars().all():
        if c.name not in LANDMARKS or not c.is_passable:
            continue
        slot = (c.location_id, c.name)
        if slot not in best or (c.x, c.y) < (best[slot].x, best[slot].y):
            best[slot] = c
    return {c.id for c in best.values()}


async def is_landmark(session, cell) -> bool:
    if cell is None or cell.name not in LANDMARKS:
        return False
    return cell.id in await keys(session, cell.location_id)


def seen_of(character) -> list:
    raw = getattr(character, "landmarks_seen", "") or ""
    try:
        return list(json.loads(raw)) if raw else []
    except (ValueError, TypeError):
        return []


def mark_seen(character, cell_id):
    seen = seen_of(character)
    if cell_id not in seen:
        seen.append(cell_id)
    character.landmarks_seen = json.dumps(seen)


def visited(character, cell) -> bool:
    return cell is not None and cell.id in seen_of(character)


async def total(session, character=None):
    """Сколько диковин в мире и сколько нашёл герой."""
    ks = await keys(session)
    if character is None:
        return 0, len(ks)
    return len(ks & set(seen_of(character))), len(ks)


async def claim(session, character, cell, rng=None):
    """Забрать награду. Один раз на героя. Возвращает (успех, строки)."""
    mark = of(cell)
    if mark is None or not await is_landmark(session, cell):
        return False, ["Здесь нет ничего примечательного."]
    if visited(character, cell):
        return False, ["Ты уже брал здесь всё, что было."]

    rng = rng or random
    mark_seen(character, cell.id)
    lines = [f"{mark['icon']} <b>{cell.name}</b>", "", f"<i>{mark['text']}</i>", ""]
    kind = mark["kind"]

    if kind == "gold":
        gold = rng.randint(20, 40) + character.level * 10
        character.gold += gold
        lines.append(f"💰 Найдено: <b>{gold}</b> 🟤")
    elif kind == "exp":
        exp = 40 + character.level * 20
        character.experience += exp
        lines.append(f"⭐ Опыт: <b>+{exp}</b>")
    elif kind == "heal":
        character.current_hp = character.max_hp
        character.current_mp = character.max_mp
        from core import death as core_death
        core_death.heal_wounds(character)
        lines.append("❤️ Силы полностью восстановлены, раны затянулись.")
    elif kind == "magic":
        stat = rng.choice(STATS)
        setattr(character, stat, getattr(character, stat, 10) + 1)
        label = {"strength": "💪 Сила", "agility": "🏃 Ловкость",
                 "intelligence": "🧠 Интеллект", "endurance": "🧱 Выносливость",
                 "luck": "🍀 Удача"}[stat]
        lines.append(f"✨ Благословение навсегда: <b>{label} +1</b>")
    else:                                        # item
        from core.models import Item, InventoryItem

        result = await session.execute(
            select(Item).where(Item.price <= 40 + character.level * 30)
        )
        pool = result.scalars().all()
        if pool:
            item = rng.choice(pool)
            session.add(InventoryItem(character_id=character.id,
                                      item_id=item.id, quantity=1))
            lines.append(f"📦 Находка: {item.icon} <b>{item.name}</b>")

    from core import factions as core_factions
    lines.extend(core_factions.award(character, "landmark_found"))
    found, all_ = await total(session, character)
    lines.append(f"\n🗺 Достопримечательностей: <b>{found}/{all_}</b>")
    await session.flush()
    return True, lines
