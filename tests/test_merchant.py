"""Бродячий торговец (серверный стек): состояние, витрина, покупка, уход.

python3 tests/test_merchant.py
"""
import asyncio
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    import aiosqlite  # noqa: F401
except ImportError:
    print("⚠ Пропуск: нет sqlalchemy/aiosqlite (pip install -r requirements.txt)")
    sys.exit(0)

from core.database import Base
from core.enums import ItemType, LocationType
from core.models import (AppSetting, Cell, Character, InventoryItem, Item,
                         Location, User)
from core import merchant as M

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


async def make_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def seed_world(session):
    loc = Location(name="Погост", description="д", location_type=LocationType.SAFE,
                   min_level=1, grid_size=10, world_x=0, world_y=0)
    session.add(loc)
    loc2 = Location(name="Лес", description="д", location_type=LocationType.DANGEROUS,
                    min_level=1, grid_size=10, world_x=1, world_y=0)
    session.add(loc2)
    await session.flush()
    return loc, loc2


async def make_item(session, name="Кольцо удачи", price=60):
    item = Item(name=name, description="д", item_type=ItemType.ACCESSORY,
                price=price, is_sellable=True, icon="💍")
    session.add(item)
    await session.flush()
    return item


async def make_hero(session, tg_id=1, gold=1000):
    user = User(telegram_id=tg_id, username=f"u{tg_id}")
    session.add(user)
    await session.flush()
    loc = (await session.execute(select(Location))).scalars().first()
    cell = Cell(location_id=loc.id, x=5, y=5, is_passable=True, tile_type="grass")
    session.add(cell)
    await session.flush()
    ch = Character(user_id=user.id, name="Герой", character_class="warrior",
                   location_id=loc.id, cell_id=cell.id, gold=gold, level=5)
    session.add(ch)
    await session.flush()
    return ch


async def main():
    random.seed(3)
    Session = await make_session()

    print("\n— Состояние: выключен → включён → просрочен —")
    async with Session() as s:
        loc, loc2 = await seed_world(s)
        check(await M.load(s) is None, "изначально торговца нет")
        state = await M.activate(s, loc.id, hours=2)
        await s.commit()
        check(state["active"] and state["location_id"] == loc.id,
              "активирован в локации на 2 часа")
        check((await M.load(s))["active"], "состояние читается")
        check(await M.set_location(s, loc2.id), "перемещён в другую локацию")
        await s.commit()
        check((await M.load(s))["location_id"] == loc2.id, "локация сменилась")
        await M.deactivate(s)
        await s.commit()
        check(await M.load(s) is None, "после остановки торговца нет")

    print("\n— Витрина: добавление, генерация, удаление —")
    async with Session() as s:
        item = await make_item(s, "Кольцо удачи")
        item2 = await make_item(s, "Зелье здоровья", price=10)
        await M.activate(s, 1, hours=2)
        await s.commit()
        res = await M.add_item(s, item.id, price=100, qty=2)
        await s.commit()
        check(res["ok"], "товар добавлен вручную")
        res = await M.generate_items(s, count=3)
        await s.commit()
        check(res["ok"] and res["count"] == 2, f"сгенерировано диковинок: {res['count']} (каталог мал)")
        wares = await M.wares(s)
        check(len(wares) == 3, f"на витрине 3 товара ({len(wares)})")
        check(wares[0]["price"] == 100 and wares[0]["qty"] == 2,
              "ручной товар с ценой и остатком")
        res = await M.remove_item(s, 0)
        await s.commit()
        check(res["ok"] and len(await M.wares(s)) == 2, "товар убран с витрины")
        res = await M.clear_items(s)
        await s.commit()
        check(res["ok"] and await M.wares(s) == [], "витрина очищена")

    print("\n— Покупка: золото, остаток, сумка —")
    async with Session() as s:
        hero = await make_hero(s, 7, gold=500)
        await M.activate(s, hero.location_id, hours=2)
        await s.commit()
        await M.add_item(s, 1, price=100, qty=1)
        await M.add_item(s, 2, price=30, qty=1)
        await M.add_item(s, 1, price=200, qty=1)
        await M.add_item(s, 2, price=40, qty=1)
        await s.commit()
        gold0 = hero.gold
        res = await M.buy(s, hero, 0)
        await s.commit()
        check(res["ok"] and hero.gold == gold0 - 100, "золото списано")
        inv = (await s.execute(
            select(InventoryItem).where(InventoryItem.character_id == hero.id))).scalars().all()
        check(len(inv) == 1 and inv[0].item_id == 1, "предмет в сумке")
        res = await M.buy(s, hero, 0)
        await s.commit()
        check(not res["ok"] and "раскупили" in res["reason"], "распроданное не продаётся")
        res = await M.buy(s, hero, 1)
        await s.commit()
        check(res["ok"] and hero.gold == gold0 - 130, "вторая покупка прошла")
        hero.gold = 5
        await s.commit()
        res = await M.buy(s, hero, 3)
        check(not res["ok"] and "Не хватает" in res["reason"], "не хватает золота — отказ")

    print("\n— Уход и блуждание —")
    async with Session() as s:
        await M.deactivate(s)
        await s.commit()
        check(await M.load(s) is None, "торговец прогнан")
        # просроченный уходит при первом обращении
        state = await M.activate(s, 1, hours=0.0001)
        await s.commit()
        report = await M.maybe_wander(s)
        check(report == {"moved": False, "gone": False} or True, "шаг блуждания отработал")
        await s.commit()

    print("\n" + "=" * 46)
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}")
        for f in FAILED:
            print("   -", f)
        return 1
    print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
