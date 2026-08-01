"""Надгробия и раны для серверного стека — паритет с engine/death.py.

Золото и часть сумки не исчезают при гибели, а ждут хозяина на месте
смерти. Дошёл обратно — вернул всё; погиб по дороге — потерял. Чужую
могилу можно обчистить, но половина рассыпается прахом.

Раны: временный штраф к статам, лечится у лекаря или проходит сам.
Числа берутся из `engine.death`, чтобы стеки не разъехались.
"""
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from engine import death as E
from core.models import Grave, InventoryItem

GRAVE_HOURS = E.GRAVE_HOURS
WOUND_MINUTES = E.WOUND_MINUTES
WOUND_PENALTY = E.WOUND_PENALTY


def _now():
    return datetime.now(timezone.utc)


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── надгробия ───────────────────────────────────────────────

async def bury(session, character, gold: int, item_ids=()):
    """Оставить надгробие на месте гибели. Одно на героя."""
    item_ids = list(item_ids or [])
    if gold <= 0 and not item_ids:
        return None
    # Старая могила рассыпается: копить золото полем нельзя.
    result = await session.execute(
        select(Grave).where(Grave.character_id == character.id)
    )
    for old in result.scalars().all():
        await session.delete(old)

    grave = Grave(
        character_id=character.id, owner_name=character.name,
        location_id=character.location_id,
        x=getattr(character, "cell_x", 0) or 0,
        y=getattr(character, "cell_y", 0) or 0,
        floor=character.floor or 0,
        gold=int(gold), items=json.dumps(item_ids),
    )
    session.add(grave)
    await session.flush()
    return grave


async def at(session, location_id, x, y, floor=0):
    """Надгробие в этой клетке или None. Этаж учитывается: могила на
    первом этаже подземелья не должна светиться на поверхности."""
    await decay(session)
    result = await session.execute(
        select(Grave).where(Grave.location_id == location_id)
                     .where(Grave.x == x).where(Grave.y == y)
                     .where(Grave.floor == (floor or 0))
    )
    return result.scalars().first()


async def mine(session, character):
    result = await session.execute(
        select(Grave).where(Grave.character_id == character.id)
    )
    return result.scalars().first()


async def claim(session, character, grave):
    """Забрать содержимое. Своё — целиком, чужое — половина.

    Гонка «кто первый до могилы» решается атомарным удалением: два
    мародёра одновременно не начистят одну и ту же могилу.
    """
    own = grave.character_id == character.id
    gold = int(grave.gold or 0)
    try:
        items = json.loads(grave.items or "[]")
    except (ValueError, TypeError):
        items = []

    # Сначала атомарно убираем могилу из мира — потом раздаём содержимое.
    from sqlalchemy import delete
    res = await session.execute(
        delete(Grave).where(Grave.id == grave.id)
    )
    if res.rowcount != 1:
        return 0, [], own                      # кто-то успел раньше

    taken_gold = gold if own else gold // 2
    taken_items = items if own else items[:len(items) // 2]
    from engine.currency import add_currency
    add_currency(character, bronze=taken_gold)
    for item_id in taken_items:
        session.add(InventoryItem(character_id=character.id,
                                  item_id=int(item_id), quantity=1))
    await session.flush()
    return taken_gold, taken_items, own


async def decay(session):
    """Убрать истлевшие надгробия."""
    result = await session.execute(select(Grave))
    limit = _now() - timedelta(hours=GRAVE_HOURS)
    gone = 0
    for g in result.scalars().all():
        if _aware(g.created_at) and _aware(g.created_at) < limit:
            await session.delete(g)
            gone += 1
    if gone:
        await session.flush()
    return gone


# ── раны ────────────────────────────────────────────────────

def wound(character, minutes=WOUND_MINUTES):
    character.wounded_until = _now() + timedelta(minutes=minutes)


def wounded(character) -> bool:
    until = _aware(getattr(character, "wounded_until", None))
    return bool(until and _now() < until)


def wound_left(character) -> int:
    until = _aware(getattr(character, "wounded_until", None))
    if not until or _now() >= until:
        return 0
    return max(1, int((until - _now()).total_seconds() // 60) + 1)


def heal_wounds(character):
    character.wounded_until = None


def penalty(character) -> float:
    """Множитель статов: раненый слабее."""
    return 1.0 - WOUND_PENALTY if wounded(character) else 1.0


def note(character) -> str:
    if not wounded(character):
        return ""
    return (f"🩸 <i>Раны кровоточат: −{int(WOUND_PENALTY * 100)}% к статам, "
            f"ещё ~{wound_left(character)} мин. Лекарь поможет.</i>")
