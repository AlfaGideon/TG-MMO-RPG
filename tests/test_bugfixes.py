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
    shop.sell_here(p, "-1")
    check(p.gold == gold and len(p.inventory) == 3,
          "sells:-1 ничего не продал")
    p.loc = 0                          # безопасная локация для кармана
    stash.put(p, "-1")
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

def _have_modules(*names):
    import importlib.util
    return all(importlib.util.find_spec(n) for n in names)


def _have_server_deps():
    return _have_modules("sqlalchemy", "aiosqlite")


def _have_bot_deps():
    return _have_modules("aiogram", "PIL")


def _have_admin_deps():
    return _have_modules("fastapi", "jinja2")


async def _make_db(path=":memory:"):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from core.database import Base
    import importlib
    importlib.import_module("core.models")   # таблицы на Base.metadata
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _world_fixture(sm):
    """Локация с сундучной клеткой и три персонажа с золотом."""
    from core.models import Cell, Character, Location, User
    async with sm() as s:
        loc = Location(name="Пустошь", description="d")
        s.add(loc)
        await s.flush()
        cell = Cell(location_id=loc.id, x=1, y=1, floor=0, has_chest=True,
                    chest_tier=2, is_passable=True)
        s.add(cell)
        users = [User(telegram_id=t) for t in (11, 22, 33)]
        s.add_all(users)
        await s.flush()
        chars = [Character(user_id=u.id, name=f"П{u.id}", gold=1000,
                           level=10, character_class="warrior",
                           location_id=loc.id, cell_id=cell.id)
                 for u in users]
        s.add_all(chars)
        await s.commit()
        return loc.id, cell.id, [c.id for c in chars]


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


# ── второй проход: гонки общих ресурсов мира ────────────────
# Файловая SQLite обязательна: :memory: (StaticPool) — одно соединение,
# параллельные писатели там не воспроизводятся честно.

def _file_db():
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    return tmp


async def test_chest_claim_race_async():
    """Двое вскрывают один сундук: лут достаётся одному."""
    print("\n— Сундук: гонка вскрытия —")
    tmp = _file_db()
    try:
        engine, sm = await _make_db(tmp.name)
        _loc, cell_id, (c1, c2, _c3) = await _world_fixture(sm)
        from datetime import timedelta
        from sqlalchemy import or_, update
        from core.dates import utcnow
        from core.models import Cell, Character

        async def open_it(cid):
            """То же, что делает bot.handlers.location.open_chest после
            фикса: условный UPDATE захватывает сундук одним запросом."""
            await asyncio.sleep(0.05)
            async with sm() as s:
                new_respawn = utcnow() + timedelta(minutes=30)
                claimed = await s.execute(
                    update(Cell)
                    .where(Cell.id == cell_id)
                    .where(Cell.has_chest == True)      # noqa: E712
                    .where(or_(Cell.chest_respawn_at.is_(None),
                               Cell.chest_respawn_at <= utcnow()))
                    .values(chest_respawn_at=new_respawn))
                if claimed.rowcount != 1:
                    await s.rollback()
                    return False
                ch = await s.get(Character, cid)
                ch.gold += 50
                await s.commit()
                return True

        r1, r2 = await asyncio.gather(open_it(c1), open_it(c2))
        check(sorted([r1, r2]) == [False, True],
              f"победитель ровно один ({r1}, {r2})")
        await engine.dispose()
    finally:
        os.unlink(tmp.name)


async def test_grave_race_async():
    """Двое мародёров: содержимое могилы раздаётся один раз."""
    print("\n— Могила: гонка мародёров —")
    tmp = _file_db()
    try:
        engine, sm = await _make_db(tmp.name)
        loc_id, _cell, (owner, m1, m2) = await _world_fixture(sm)
        from core import death
        from core.models import Character

        async with sm() as s:
            class C:
                id = owner
                name = "Покойный"
                location_id = loc_id
                cell_x = 5
                cell_y = 5
                floor = 0
            await death.bury(s, C(), 1000, item_ids=[])
            await s.commit()

        async def rob(cid):
            await asyncio.sleep(0.05)
            async with sm() as s:
                ch = await s.get(Character, cid)
                grave = await death.at(s, loc_id, 5, 5, floor=0)
                if grave is None:
                    return 0
                gold, _items, _own = await death.claim(s, ch, grave)
                await s.commit()
                return gold

        g1, g2 = await asyncio.gather(rob(m1), rob(m2))
        check(sorted([g1, g2]) == [0, 500],
              f"золото роздано однократно ({g1}, {g2})")
        await engine.dispose()
    finally:
        os.unlink(tmp.name)


async def test_boss_double_finish_async():
    """Два добивших удара: награда раздаётся однократно."""
    print("\n— Мировой босс: двойное добивание —")
    tmp = _file_db()
    try:
        engine, sm = await _make_db(tmp.name)
        loc_id, _cell, (c1, c2, _c3) = await _world_fixture(sm)
        from core import worldevents
        from core.models import Character

        async with sm() as s:
            await worldevents.summon_boss(s, "leviathan",
                                          location_id=loc_id, hours=6)
            await s.commit()

        async def hit(cid, dmg):
            async with sm() as s:
                ch = await s.get(Character, cid)
                hp, _ph = await worldevents.hit_boss(s, ch, dmg)
                await s.commit()
                return hp

        await hit(c1, 2000)
        await hit(c2, 1500)
        r = await asyncio.gather(hit(c1, 600), hit(c2, 600))
        check(0 in r, f"босс пал ({r})")

        async with sm() as s:
            golds = []
            for cid in (c1, c2):
                ch = await s.get(Character, cid)
                golds.append(ch.gold)
        # пул награды = max_hp*0.5 = 2000 (+ минималки 10). Вдвое больше —
        # значит, _reward_boss отработал дважды (исходный баг).
        total_reward = sum(g - 1000 for g in golds)
        check(10 <= total_reward <= 2020,
              f"награда однократна: пул=2000, выдано={total_reward}")
        await engine.dispose()
    finally:
        os.unlink(tmp.name)


async def test_mob_claim_race_async():
    """Двое бьют одного моба: захват одним UPDATE (как в start_cell_battle)."""
    print("\n— Моб: гонка захвата —")
    tmp = _file_db()
    try:
        engine, sm = await _make_db(tmp.name)
        loc_id, _cell, (c1, c2, _c3) = await _world_fixture(sm)
        from sqlalchemy import or_, update
        from core.models import Mob, MobSpawn

        async with sm() as s:
            mob = Mob(name="Волк", description="", hp=10, damage=1,
                      defense=0, level=1)
            s.add(mob)
            await s.flush()
            spawn = MobSpawn(mob_id=mob.id, home_location_id=loc_id,
                             location_id=loc_id, x=1, y=1, is_alive=True)
            s.add(spawn)
            await s.commit()
            spawn_id = spawn.id

        async def engage(cid):
            await asyncio.sleep(0.05)
            async with sm() as s:
                res = await s.execute(
                    update(MobSpawn)
                    .where(MobSpawn.id == spawn_id)
                    .where(MobSpawn.is_alive == True)    # noqa: E712
                    .where(or_(MobSpawn.engaged_by_id.is_(None),
                               MobSpawn.engaged_by_id == cid))
                    .values(engaged_by_id=cid))
                await s.commit()
                return res.rowcount == 1

        r1, r2 = await asyncio.gather(engage(c1), engage(c2))
        check(sorted([r1, r2]) == [False, True],
              f"моба захватил один ({r1}, {r2})")
        await engine.dispose()
    finally:
        os.unlink(tmp.name)


def test_display_timezones():
    """Display-код карточек лота и тикера порталов выдерживает aware-даты."""
    print("\n— Таймзоны во втором проходе —")
    from datetime import datetime, timedelta, timezone
    from core import dates

    aware_exp = datetime.now(timezone.utc) + timedelta(hours=5)
    hours = int((dates.aware(aware_exp) - dates.utcnow()).total_seconds() // 3600)
    check(hours in (4, 5), f"остаток лота на aware-дате: {hours}ч")

    opened = datetime.now(timezone.utc) - timedelta(seconds=100)
    left = max(0, int(7200 - (dates.utcnow()
                              - dates.aware(opened)).total_seconds()))
    check(7000 <= left <= 7100, f"тикер портала: {left}с")

    # старый код (aware - naive) на Postgres падал бы TypeError — страж
    try:
        _ = aware_exp - datetime.utcnow()
        crashed = False
    except TypeError:
        crashed = True
    check(crashed, "исходный код действительно был уязвим (TypeError)")


def test_dungeon_defeat_penalty():
    """Смерть в подземелье должна лишать сумки, как смерть на поверхности."""
    print("\n— Подземелье: поражение с последствиями —")
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "bot", "handlers", "dungeon.py"),
        encoding="utf-8").read()
    defeat = src[src.index('state["char_hp"] <= 0'):]
    defeat = defeat[:defeat.index("await callback.message.edit_text")]
    check("_lose_bag" in defeat, "ветка поражения зовёт _lose_bag")


async def test_serialize_middleware_async():
    """Поюзерный замок: двойной тап ждёт, сосед не мешает."""
    print("\n— Middleware: сериализация поюзерная —")
    from bot.middlewares.serialize import SerializeUserMiddleware

    mw = SerializeUserMiddleware()

    class U:
        def __init__(self, i):
            self.id = i

    class Ev:
        def __init__(self, i):
            self.from_user = U(i)

    running = {"now": 0, "max": 0}

    async def handler(ev, data):
        running["now"] += 1
        running["max"] = max(running["max"], running["now"])
        await asyncio.sleep(0.05)
        running["now"] -= 1

    await asyncio.gather(mw(handler, Ev(1), {}), mw(handler, Ev(1), {}))
    check(running["max"] == 1, "апдейты одного пользователя не пересекаются")
    running["max"] = 0
    await asyncio.gather(mw(handler, Ev(1), {}), mw(handler, Ev(2), {}))
    check(running["max"] == 2, "разные пользователи идут параллельно")


async def test_dungeon_defeat_loses_bag_async():
    """Поражение в подземелье снимает пятину золота и ставит надгробие
    (та же _lose_bag, что у обычного боя)."""
    print("\n— Подземелье: _lose_bag при поражении —")
    engine, sm = await _make_db()
    _loc_id, _cell_id, (c1, _c2, _c3) = await _world_fixture(sm)
    from sqlalchemy import select
    from bot.handlers.battle import _lose_bag
    from core.models import Character, Grave

    async with sm() as s:
        ch = await s.get(Character, c1)
        note = await _lose_bag(s, ch)
        check(ch.gold == 800, f"пятина золота осталась надгробием ({ch.gold})")
        check("Осталось на месте гибели" in note, "текст поражения честный")
        grave = await s.scalar(
            select(Grave).where(Grave.character_id == c1))
        check(grave is not None and grave.gold == 200,
              "надгробие с золотом создано")
        check(ch.wounded_until is not None, "рана выставлена")
    await engine.dispose()


async def test_editor_cell_garbage_async():
    """Мусор в числовых полях редактора клетки — 303-отказ, не 500."""
    print("\n— Админка: нечисловые поля клетки —")
    import admin.main as A
    from core.models import Cell, Location

    engine, sm = await _make_db()
    async with sm() as s:
        loc = Location(name="L", description="d")
        s.add(loc)
        await s.flush()
        cell = Cell(location_id=loc.id, x=2, y=3, is_passable=True)
        s.add(cell)
        await s.commit()
        cell_id, loc_id = cell.id, loc.id

    A.guard = lambda *a, **k: None
    A.async_session = sm

    class FakeRequest:
        query_params = {}

    async def save(**over):
        base = dict(name="К", description="", tile_type="road",
                    is_passable=True, has_npc=False, npc_name="",
                    npc_type="", npc_station="", npc_dialogue="",
                    has_chest=False, chest_tier=1, has_house=False,
                    has_tree=False, has_campfire=False, image_url="",
                    image=None, target_location_id="", target_x="",
                    target_y="", target_floor="", dungeon_template_id="")
        base.update(over)
        return await A.editor_cell_save(FakeRequest(), cell_id, **base)

    resp = await save(target_location_id="abc")
    ok = getattr(resp, "status_code", None) == 303 and "error=" in (
        getattr(resp, "headers", {}).get("location", ""))
    check(ok, "мусор -> 303 с ошибкой, не 500")
    async with sm() as s:
        cell = await s.get(Cell, cell_id)
        check(cell.target_location_id is None, "невалидный ввод не записан")

    resp2 = await save(target_location_id=str(loc_id), target_x="4",
                       target_y="5", target_floor="1")
    check(getattr(resp2, "status_code", None) == 303, "валидный ввод сохранён")
    async with sm() as s:
        cell = await s.get(Cell, cell_id)
        check(cell.target_location_id == loc_id and cell.target_floor == 1,
              "портал записан корректно")
    await engine.dispose()


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
        # второй проход
        asyncio.run(test_chest_claim_race_async())
        asyncio.run(test_grave_race_async())
        asyncio.run(test_boss_double_finish_async())
        asyncio.run(test_mob_claim_race_async())
        test_display_timezones()
        test_dungeon_defeat_penalty()
    else:
        print("⚠ Пропуск серверной части: нет sqlalchemy/aiosqlite "
              "(pip install -r requirements.txt)")
    if _have_server_deps() and _have_bot_deps():
        asyncio.run(test_serialize_middleware_async())
        asyncio.run(test_dungeon_defeat_loses_bag_async())
    else:
        print("⚠ Пропуск бот-тестов: нет aiogram/Pillow")
    if _have_server_deps() and _have_admin_deps():
        asyncio.run(test_editor_cell_garbage_async())
    else:
        print("⚠ Пропуск админ-теста: нет fastapi/jinja2")
    print("\n" + "=" * 46)
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}: {', '.join(FAILED)}")
        return 1
    print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
