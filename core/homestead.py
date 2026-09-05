"""Дом героя на сервере (IDEAS-next, пункт 8).

Правила — не здесь: цены, вместимость и доля лечения живут в
``engine/homestead.py`` и переэкспортируются оттуда, как у осад
(``core/worldevents.py`` ← ``engine/siege.py``). Здесь только работа с БД:
уровни на ``Character`` и флаг ``InventoryItem.in_home``.

Сундук — третий сейф после сумки и кармана: сумка часть выпадает при
гибели, карман доступен из любых безопасных земель, а дом — только из
своих дверей: он привязан к локации, где герой осел, и за это вмещает
на порядок больше.
"""
from __future__ import annotations

from sqlalchemy import select

from core.models import InventoryItem, Location

from engine.homestead import (  # единый источник чисел для обоих стеков
    LEVEL_TITLES,
    RULES,
)
from engine.homestead import capacity, rest_amount, rest_share, upgrade_cost

from core import stash as core_stash

__all__ = ["RULES", "LEVEL_TITLES", "capacity", "upgrade_cost", "rest_amount",
           "settled", "at_home", "free", "items", "settle", "upgrade", "put",
           "take", "rest_share_for", "home_state"]


def settled(character) -> bool:
    return int(getattr(character, "house_level", 0) or 0) > 0


def at_home(character) -> bool:
    """Дома ли герой: та же проверка, что у движка, но на колонках БД."""
    return (settled(character)
            and character.home_location_id is not None
            and int(character.home_location_id) == int(character.location_id or -1))


def capacity_for(character) -> int:
    level = int(getattr(character, "house_level", 0) or 0)
    return capacity(level if settled(character) else 0,
                    core_stash.is_vip(character))


async def free(session, character) -> int:
    return max(0, capacity_for(character) - len(await items(session, character)))


async def items(session, character):
    """Что лежит в домашнем сундуке."""
    result = await session.execute(
        select(InventoryItem)
        .where(InventoryItem.character_id == character.id)
        .where(InventoryItem.in_home == True)  # noqa: E712
    )
    return result.scalars().all()


async def settle(session, character) -> tuple:
    """Осесть: платим бронзой, дом привязывается к текущей локации."""
    from engine.currency import deduct_currency

    if settled(character):
        return False, "Дом у тебя уже есть — загляни в него."
    location = await session.get(Location, character.location_id)
    if not core_stash.safe_here(location):
        return False, "Оситься можно только в безопасных землях. Погост подойдёт."
    cost = RULES["cost"][1]
    if not deduct_currency(character, cost):
        return False, f"На въезд не хватает: нужно {cost}🟤."
    character.house_level = 1
    character.home_location_id = character.location_id
    await session.flush()
    return True, "🏠 Ты осел. Сундук переживёт что угодно — дома."


async def upgrade(session, character) -> tuple:
    from engine.currency import deduct_currency

    if not settled(character):
        return False, "Сначала оседляйся."
    cost = upgrade_cost(character.house_level)
    if cost is None:
        return False, "Дальше только башня. Это предел."
    if not deduct_currency(character, cost):
        return False, f"На надстройку нужно {cost}🟤."
    character.house_level = int(character.house_level) + 1
    await session.flush()
    title = LEVEL_TITLES.get(character.house_level, "Дом")
    return True, f"⬆️ {title} — места больше!"


async def put(session, character, inv_item) -> tuple:
    """Вещь → сундук. Только у своих дверей (в отличие от кармана)."""
    if inv_item.in_home:
        return False, "Эта вещь уже в сундуке."
    if inv_item.in_stash:
        return False, "Сначала достань её из кармана."
    if not at_home(character):
        return False, "Сундук стоит дома — зайди в свои двери."
    if await free(session, character) <= 0:
        return False, f"Сундук полон: {capacity_for(character)} ячеек."
    inv_item.in_home = True
    inv_item.is_equipped = False          # спрятанное нельзя носить
    await session.flush()
    return True, "🏠 Убрано в домашний сундук."


async def take(session, character, inv_item) -> tuple:
    if not inv_item.in_home:
        return False, "Эта вещь и так в сумке."
    if not at_home(character):
        return False, "Сундук дома — там и открывают."
    inv_item.in_home = False
    await session.flush()
    return True, "🎒 Возвращено в сумку."


async def rest_share_for(session, character) -> float:
    """Доля восстановления за привал: у очага щедрее, чем у костра."""
    return rest_share(int(getattr(character, "house_level", 0) or 0),
                      at_home(character), core_stash.is_vip(character))


async def home_state(session, character) -> dict:
    """Всё, что видит экран дома: уровень, сундук, цена следующего шага."""
    stored = await items(session, character)
    level = int(getattr(character, "house_level", 0) or 0)
    return {
        "settled": settled(character),
        "at_home": at_home(character),
        "level": level,
        "title": LEVEL_TITLES.get(level, "🏠 Дом"),
        "count": len(stored),
        "capacity": capacity_for(character),
        "vip": core_stash.is_vip(character),
        "next_cost": upgrade_cost(level) if settled(character)
        else RULES["cost"][1],
    }
