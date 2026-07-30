"""Защищённый карман в серверном стеке — паритет с engine/stash.py.

Поднимает временную SQLite-базу. Без sqlalchemy/aiosqlite набор
аккуратно пропускается, как соседние серверные тесты.

python3 tests/test_server_stash.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                        create_async_engine)
    import aiosqlite  # noqa: F401
except ImportError:
    print("⚠ Пропуск: нет sqlalchemy/aiosqlite (pip install -r requirements.txt)")
    sys.exit(0)

from core import stash as stash_core
from core.database import Base
from core.enums import CharacterClass, ItemType, LocationType
from core.models import (AppSetting, Character, InventoryItem, Item, Location,
                         User)

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


async def seed(session):
    """Герой, безопасная и опасная локации, десяток вещей в сумке."""
    safe = Location(name="Погост", description="дом",
                    location_type=LocationType.SAFE, world_x=0, world_y=0)
    risky = Location(name="Лес", description="жуть",
                     location_type=LocationType.DANGEROUS, world_x=1, world_y=0)
    session.add_all([safe, risky])
    await session.flush()

    user = User(telegram_id=1, username="tester")
    session.add(user)
    await session.flush()
    ch = Character(user_id=user.id, name="Гидеон", level=5,
                   character_class=CharacterClass.WARRIOR,
                   location_id=safe.id, current_hp=100, max_hp=100)
    session.add(ch)
    await session.flush()

    items = []
    for i in range(10):
        it = Item(name=f"Вещь {i}", description="", item_type=ItemType.WEAPON,
                  price=10 + i)
        session.add(it)
        items.append(it)
    await session.flush()
    for it in items:
        session.add(InventoryItem(character_id=ch.id, item_id=it.id, quantity=1))
    await session.flush()
    return ch, safe, risky


async def bag_of(session, ch):
    from sqlalchemy import select
    result = await session.execute(
        select(InventoryItem).where(InventoryItem.character_id == ch.id)
    )
    return result.scalars().all()


async def run():
    print("\n— Размер кармана и VIP —")
    maker = await make_session()
    async with maker() as session:
        ch, safe, risky = await seed(session)
        cap = await stash_core.capacity(session, ch)
        check(cap == stash_core.SLOTS, f"базовый размер {cap}")

        ch.is_vip = True
        ch.vip_until = None
        cap = await stash_core.capacity(session, ch)
        check(cap == stash_core.SLOTS + stash_core.VIP_BONUS,
              f"VIP расширяет до {cap}")
        ch.is_vip = False

    print("\n— Настройки из админки действуют —")
    maker = await make_session()
    async with maker() as session:
        ch, safe, risky = await seed(session)
        await stash_core.set_tunables(session, {"stash_slots": 8,
                                                "stash_vip_bonus": 5})
        await session.commit()
        check(await stash_core.capacity(session, ch) == 8, "новый размер применён")
        ch.is_vip = True
        ch.vip_until = None
        check(await stash_core.capacity(session, ch) == 13, "и прибавка VIP тоже")

        await stash_core.set_tunables(session, {"stash_loss_share": 5})
        await session.commit()
        check(await stash_core.tune(session, "stash_loss_share") == 1.0,
              "доля больше 1 обрезается")
        await stash_core.set_tunables(session, {"stash_slots": "мусор"})
        await session.commit()
        check(await stash_core.tune(session, "stash_slots") == 8,
              "мусор игнорируется")
        await stash_core.set_tunables(session, {"stash_slots": ""})
        await session.commit()
        check(await stash_core.tune(session, "stash_slots") == stash_core.SLOTS,
              "пустое поле возвращает умолчание")

    print("\n— Перекладывание и лимит —")
    maker = await make_session()
    async with maker() as session:
        ch, safe, risky = await seed(session)
        bag = await bag_of(session, ch)

        ok, _ = await stash_core.put(session, ch, bag[0])
        await session.flush()
        check(ok and bag[0].in_stash, "вещь ушла в карман")

        for inv in bag[1:stash_core.SLOTS]:
            await stash_core.put(session, ch, inv)
        await session.flush()
        check(len(await stash_core.stashed(session, ch)) == stash_core.SLOTS,
              "карман заполнен")

        ok, msg = await stash_core.put(session, ch, bag[stash_core.SLOTS])
        check(not ok and "полон" in msg, "сверх лимита не влезает")

        ok, _ = await stash_core.take(session, ch, bag[0])
        await session.flush()
        check(ok and not bag[0].in_stash, "вещь вернулась в сумку")

    print("\n— Надетое снимается при уборке —")
    maker = await make_session()
    async with maker() as session:
        ch, safe, risky = await seed(session)
        bag = await bag_of(session, ch)
        bag[0].is_equipped = True
        await stash_core.put(session, ch, bag[0])
        await session.flush()
        check(not bag[0].is_equipped, "спрятанное больше не надето")

    print("\n— Только в безопасных землях —")
    maker = await make_session()
    async with maker() as session:
        ch, safe, risky = await seed(session)
        check(stash_core.safe_here(safe), "в Погосте карман открыт")
        check(not stash_core.safe_here(risky), "в лесу закрыт")
        check(not stash_core.safe_here(None), "без локации закрыт")

    print("\n— Потери при гибели —")
    maker = await make_session()
    async with maker() as session:
        ch, safe, risky = await seed(session)
        bag = await bag_of(session, ch)
        for inv in bag[:3]:
            await stash_core.put(session, ch, inv)
        bag[3].is_equipped = True
        await session.flush()

        lost = await stash_core.drop_on_death(session, ch)
        check(lost, f"часть сумки выпала: {len(lost)}")
        check(all(not inv.in_stash for inv in lost), "карман не тронут")
        check(all(not inv.is_equipped for inv in lost), "надетое не теряется")

        await stash_core.set_tunables(session, {"stash_loss_share": 1.0})
        await session.commit()
        lost = await stash_core.drop_on_death(session, ch)
        losable = [i for i in await bag_of(session, ch)
                   if not i.in_stash and not i.is_equipped]
        check(len(lost) == len(losable), "при 100% выпадает всё, что можно")

        await stash_core.set_tunables(session, {"stash_loss_share": 0.0})
        await session.commit()
        lost = await stash_core.drop_on_death(session, ch)
        check(len(lost) == 1, "при 0% выпадает хотя бы одна вещь")

    print("\n— Паритет чисел с браузерным стеком —")
    from engine import stash as engine_stash
    check(engine_stash.SLOTS == stash_core.SLOTS, "размер кармана совпадает")
    check(engine_stash.VIP_BONUS == stash_core.VIP_BONUS, "прибавка VIP совпадает")
    check(engine_stash.LOSS_SHARE == stash_core.LOSS_SHARE, "доля потерь совпадает")
    check(set(engine_stash.TUNABLES) == set(stash_core.TUNABLES),
          "набор настроек одинаковый")
    check(engine_stash.SAFE_TYPES == stash_core.SAFE_TYPES,
          "где можно перекладывать — тоже")


def main():
    asyncio.run(run())
    print("\n" + "=" * 46)
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}:")
        for f in FAILED:
            print("   -", f)
        return 1
    print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
