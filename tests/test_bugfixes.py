"""Регрессии на баги, найденные ручным аудитом поверх основных наборов.

Сюда попадают сценарии, которые остальные наборы не покрывали:
гонки аукциона, исчезновение тварей при побеге, таймзоны Postgres,
отрицательные индексы в колбэках, HTML в именах.

python3 tests/test_bugfixes.py
"""
import asyncio
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


def fresh():
    from engine.storage import Store
    from webapp.backend import MemoryStorage
    store = Store(MemoryStorage())
    store.settings["cataclysm_notify"] = False
    store.settings["cataclysm_auto"] = False
    return store


def hero(store, game, tg_id=1):
    p = store.player(tg_id, "Герой")
    game.handle(p, "make:warrior")
    p.max_hp = p.hp = 99999
    p.strength = 9999
    p.level = 50
    return p


# ── браузерный стек ─────────────────────────────────────────

def test_flee_restores_reinforcements():
    """Побег из боя со сворой не должен стирать тварей из мира."""
    print("\n— Побег из боя со сворой —")
    from engine import cataclysm, combat, data
    from engine import world as W
    from engine.game import Game

    store = fresh()
    game = Game(store)
    p = hero(store, game)

    random.seed(11)
    spot = None
    for c in sorted(store.world.values(), key=lambda c: c.key):
        if c.mob < 0 or not c.passable or data.LOCATIONS[c.loc][2] != "dangerous":
            continue
        neigh = [W.cell_at(store.world, c.loc, c.x + dx, c.y + dy, 0)
                 for dx, dy in W.DIRS.values()]
        if sum(1 for n in neigh if n is not None and n.mob >= 0) >= 1:
            spot = c
            break
    check(spot is not None, "нашлась клетка с тварью и соседом")

    p.loc, p.x, p.y = spot.loc, spot.x, spot.y
    before = sum(1 for c in store.world.values() if c.mob >= 0)

    # включаем «катаклизм», чтобы подкрепление пришло гарантированно
    orig = cataclysm.effects
    cataclysm.effects = lambda s, loc: {"mob_rate": 1.0, "damage": 1.0,
                                        "loot": 1.0, "gold": 1.0, "rest": 1.0,
                                        "ambush": 0.0, "join": 1.0}
    try:
        combat.start(p, spot.mob)
        combat.reinforce(p, store)
        check(len(p.combat["queue"]) >= 1, "подкрепление встало в очередь")
        random.seed(2)
        for _ in range(60):
            combat.action(p, "flee", store.world, store)
            if not p.combat:
                break
            p.hp = 99999
        check(not p.combat, "герой сбежал")
    finally:
        cataclysm.effects = orig
    after = sum(1 for c in store.world.values() if c.mob >= 0)
    check(after == before, f"твари вернулись на клетки ({before} → {after})")


def test_victory_respawns_at_origin():
    """Убитая со стороны тварь воскресает дома, а не под игроком."""
    print("\n— Респавн на родной клетке —")
    from engine import combat, data
    from engine.game import Game

    store = fresh()
    game = Game(store)
    p = hero(store, game)
    cell = next(c for c in store.world.values()
                if c.mob >= 0 and c.passable
                and data.LOCATIONS[c.loc][2] == "dangerous")
    home_key = cell.key
    p.loc, p.x, p.y = cell.loc, cell.x, cell.y - 1
    mob_idx = cell.mob
    cell.mob = -1                     # так делает behavior.hunters_near
    combat.start(p, mob_idx, origin=home_key)
    random.seed(3)
    while p.combat:
        combat.action(p, "hit", store.world, store)
        p.hp = 99999
    home = store.world.get(home_key)
    mine = store.world.get(f"{p.loc}:{p.x}:{p.y}")
    check(home.mob_at > 0, "респавн запланирован на родной клетке")
    check(not mine.mob_at, "клетка игрока не получила чужой респавн")


def test_negative_positions():
    """Отрицательная позиция в колбэке не должна адресовать хвост списка."""
    print("\n— Отрицательные позиции —")
    from engine import inventory, shop, stash
    from engine.game import Game

    store = fresh()
    game = Game(store)
    p = hero(store, game)
    p.inventory += [0, 1, 2]
    gold = p.gold
    r = shop.sell_here(p, "-1")
    check(p.gold == gold and len(p.inventory) == 3,
          "sells:-1 ничего не продал")
    p.loc = 0                          # безопасная локация для кармана
    r = stash.put(p, "-1")
    check(len(p.inventory) == 3, "stput:-1 ничего не спрятал")
    equipped_before = dict(p.equipped)
    inventory.equip(p, "-1")
    check(p.equipped == equipped_before, "on:-1 ничего не надел")


def test_lot_ids_unique():
    """Два лота, выставленных подряд, получают разные id."""
    print("\n— Уникальность id лотов —")
    from engine import auction, items
    from engine.game import Game

    store = fresh()
    game = Game(store)
    p = hero(store, game)
    random.seed(0)
    ids = set()
    for _ in range(20):
        inst = items.create(store, 0, source="mob", owner=p.tg_id)
        p.inventory.append(0)
        lot, _msg = auction.list_item(store, p, inst["uid"], 10)
        if lot is None:
            break
        ids.add(lot["id"])
        auction.cancel(store, p, lot["id"])
    check(len(ids) >= 15, f"id уникальны ({len(ids)} шт.)")


def test_clean_name():
    """HTML в имени героя вычищается на входе."""
    print("\n— Имя без HTML —")
    from engine import rules
    check(rules.clean_name("<b>Злой</b>") == "bЗлой/b",
          "теги удаляются")
    check(rules.clean_name("   ") != "", "пустое имя заменяется")
    check("&" not in rules.clean_name("a&b"), "амперсанд удаляется")


def test_faction_deeds():
    """Тематическая неприязнь в таблице поступков (паритет стеков)."""
    print("\n— Фракции: неприязнь в DEEDS —")
    from engine import factions as F
    store = fresh()
    p = hero(store, __import__("engine.game", fromlist=["Game"]).Game(store))
    F.award(store, p, "undead_slain")
    check(F.value(p, "cult") < 0, "культ недоволен упокоенной нежитью")
    check(F.value(p, "guard") > 0, "стража довольна")
    p.reputation = {}
    F.award(store, p, "grave_looted")
    check(F.value(p, "guard") < 0, "стража против мародёрства")


# ── серверный стек (нужны sqlalchemy/aiosqlite) ─────────────

def _have_server_deps():
    try:
        import sqlalchemy  # noqa: F401
        import aiosqlite  # noqa: F401
        return True
    except ImportError:
        return False


async def _make_db():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from core.database import Base
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _lot_fixture(sm, price=500):
    from datetime import datetime, timedelta, timezone
    from core.enums import ItemType
    from core.models import (AuctionLot, Character, Item, ItemInstance, User)
    async with sm() as s:
        us = [User(telegram_id=i) for i in (1, 2, 3)]
        s.add_all(us)
        await s.flush()
        seller = Character(user_id=us[0].id, name="S", gold=0, level=10,
                           character_class="warrior")
        b1 = Character(user_id=us[1].id, name="B1", gold=100000, level=10,
                       character_class="warrior")
        b2 = Character(user_id=us[2].id, name="B2", gold=100000, level=10,
                       character_class="warrior")
        s.add_all([seller, b1, b2])
        await s.flush()
        item = Item(name="Меч", description="", item_type=ItemType.WEAPON,
                    price=100, level_requirement=1, is_sellable=True)
        s.add(item)
        await s.flush()
        inst = ItemInstance(uid="IT-BFX", item_id=item.id,
                            owner_character_id=None)
        s.add(inst)
        await s.flush()
        lot = AuctionLot(instance_id=inst.id, item_id=item.id,
                         seller_id=seller.id, seller_name="S", price=price,
                         status="active",
                         expires_at=datetime.now(timezone.utc)
                         + timedelta(hours=1))
        s.add(lot)
        await s.commit()
        return (seller.id, b1.id, b2.id, lot.id, inst.id)


async def test_auction_race_async():
    print("\n— Аукцион: гонка двух покупателей —")
    from sqlalchemy import func, select
    from core import auction as core_auction
    from core.models import AuctionLot, Character, InventoryItem

    _engine, sm = await _make_db()
    seller_id, b1, b2, lot_id, inst_id = await _lot_fixture(sm)

    async def buy(cid):
        async with sm() as s:
            buyer = await s.get(Character, cid)
            lot = await s.get(AuctionLot, lot_id)
            r = await core_auction.buy_lot(s, buyer, lot)
            await s.commit()
            return r["ok"]

    results = await asyncio.gather(buy(b1), buy(b2))
    async with sm() as s:
        granted = await s.scalar(
            select(func.count(InventoryItem.id))
            .where(InventoryItem.instance_id == inst_id))
        seller = await s.get(Character, seller_id)
        check(sorted(results) == [False, True],
              f"победитель ровно один {results}")
        check(granted == 1, "вещь выдана один раз")
        check(seller.gold == 475, f"продавцу начислено однократно ({seller.gold})")


async def test_grave_floor_async():
    print("\n— Могилы: этаж учитывается —")
    from core import death
    _engine, sm = await _make_db()

    class C:
        id = 1
        name = "Герой"
        location_id = 1
        cell_x = 5
        cell_y = 6
        floor = 1

    async with sm() as s:
        await death.bury(s, C(), 100)
        await s.commit()
        check(await death.at(s, 1, 5, 6, floor=1) is not None,
              "могила находится на своём этаже")
        check(await death.at(s, 1, 5, 6, floor=0) is None,
              "с другого этажа могилы не видно")


def test_timezones():
    print("\n— Таймзоны (Postgres-симуляция) —")
    from datetime import datetime, timedelta, timezone
    from core import dungeons

    class Tpl:
        is_active = True
        portal_closed_at = None
        # asyncpg вернёт aware datetime для timestamptz
        portal_opened_at = datetime.now(timezone.utc) - timedelta(hours=3)

    try:
        check(dungeons.is_portal_open(Tpl()) is False,
              "aware-время не падает, портал просрочен")
    except TypeError:
        check(False, "aware-время не падает, портал просрочен")

    Tpl.portal_opened_at = datetime.now(timezone.utc)
    check(dungeons.is_portal_open(Tpl()) is True, "свежий портал открыт")

    from core import vip

    class Ch:
        is_vip = True
        vip_until = datetime.now(timezone.utc) - timedelta(days=1)

    check(vip.is_vip_active(Ch()) is False, "истёкший aware-VIP не активен")

    class Ch2:
        is_vip = True
        vip_until = "мусор вместо даты"

    check(vip.is_vip_active(Ch2()) is False,
          "битые данные — fail-closed, а не вечный VIP")


def main():
    test_flee_restores_reinforcements()
    test_victory_respawns_at_origin()
    test_negative_positions()
    test_lot_ids_unique()
    test_clean_name()
    test_faction_deeds()
    if _have_server_deps():
        asyncio.run(test_auction_race_async())
        asyncio.run(test_grave_floor_async())
        test_timezones()
    else:
        print("⚠ Пропуск серверной части: нет sqlalchemy/aiosqlite "
              "(pip install -r requirements.txt)")
    print("\n" + "=" * 46)
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}: {', '.join(FAILED)}")
        return 1
    print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
