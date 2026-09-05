"""Дом героя: правила, сундук, отдых и подключение (IDEAS-next, пункт 8).

Запуск: python3 -m pytest -q tests/test_homestead.py

Закрепляем:
* правила (вместимость, цены, доля лечения) — чистые функции
  `engine/homestead.py`, общие для обоих стеков: сервер переэкспортирует
  их, а не хранит копию;
* браузерный поток на store: осесть → сложить → уехать (доступ закрыт) →
  вернуться → достать; отдых у очага лечит сильнее костра;
* серверный поток на БД: то же самое + сундук не трогаем при гибели
  (`core/stash.drop_on_death`) и из сундука нельзя ничего подарить;
* подключение: колбэки бота, карточка вещи, манифест браузера.
"""
import ast
import json
import os
import sys

import pytest
from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _seed import pin, unique_id, unique_name  # noqa: E402

pin(871)

from engine import homestead as H

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── чистые правила ─────────────────────────────────────────

def test_capacity_ladder_and_vip_second_floor():
    assert H.capacity(0) == 0                         # дома нет — сундука нет
    assert H.capacity(1) == H.RULES["slots"][1] == 12
    assert H.capacity(3) == 40
    assert H.capacity(2, vip=True) == 24 + H.RULES["vip_bonus"]
    # цены растут, а после 3-го уровня надстраивать нечего
    assert H.RULES["cost"][1] < H.RULES["cost"][3]
    assert H.upgrade_cost(3) is None and H.upgrade_cost(2) == 15000


def test_rest_amount_keeps_campfire_exact():
    # у костра — прежнее целочисленное деление, ни на единицу не съехало
    for hp in (7, 100, 101, 999):
        assert H.rest_amount(hp, H.RULES["camp_share"]) == max(1, hp // 3)
    # дома — по доле, но не выше максимума
    assert H.rest_amount(100, 0.5) == 50
    assert H.rest_amount(100, 1.0) == 100


def test_rest_share_follows_house_and_place():
    assert H.rest_share(2, at_home=False) == H.RULES["camp_share"]
    assert H.rest_share(0, at_home=True) == H.RULES["camp_share"]  # не осел
    assert H.rest_share(1, at_home=True) == 0.5
    assert H.rest_share(1, at_home=True, vip=True) == 1.0          # второй этаж


def test_server_rules_are_the_same_object():
    from core import homestead as core_home
    assert core_home.RULES is H.RULES


# ── браузерный поток ───────────────────────────────────────

def _store():
    from engine.storage import Store
    from webapp.backend import MemoryStorage
    return Store(MemoryStorage())


def _hero(**kw):
    from engine import data
    from engine.models import Player
    p = Player(tg_id=unique_id(), name=unique_name("Home"), level=5,
               bronze=25000, **kw)
    for i, l in enumerate(data.LOCATIONS):        # якорь — первая safe-земля
        if l[2] == "safe":
            p.loc = i
            return p
    raise AssertionError("нет безопасной локации")


def test_engine_flow_settle_fill_take_away():
    st = _store()
    p = _hero()
    assert "осел" in H.settle(p, st).alert
    assert p.house_level == 1 and p.home_loc == p.loc
    assert "уже есть" in H.settle(p, st).alert        # второй раз отказ

    p.inventory.extend([0, 1, 2])
    assert "В сундук" in H.put(p, 0, store=st).alert
    assert len(p.home) == 1 and len(p.inventory) == 2
    home_at = p.loc
    p.loc += 1                                     # уехал в опасные земли
    assert "дома" in H.put(p, 0).alert
    assert "дома" in H.take(p, 0).alert
    p.loc = home_at
    assert "сумке" in H.take(p, 0, store=st).alert or "🎒" in H.take(p, 0).alert

    # вместимость: затолкать больше 12 нельзя
    p.inventory.extend([0] * 20)
    for i in range(30):
        H.put(p, 0, store=st)
    assert len(p.home) <= H.cap_of(p)

    rows = []
    H.button(st, p, rows)
    assert rows and rows[0][0][1].startswith("house")


def test_engine_rest_hearth_beats_campfire():
    from engine import explore
    st = _store()
    p = _hero()
    H.settle(p, st)
    p.hp = 1
    explore.rest(p, st)
    at_hearth = p.hp
    p.hp = 1
    p.loc += 1
    explore.rest(p, st)
    assert at_hearth > p.hp                        # очаг лечит сильнее


# ── серверный поток ────────────────────────────────────────

@pytest.mark.asyncio
async def test_server_flow_home_locks_and_death_safe():
    from core import homestead as core_home
    from core import stash as core_stash
    from core.database import async_session
    from core.models import Character, InventoryItem, Item, Location, User

    from core.enums import ItemType, LocationType

    async with async_session() as session:
        safe = Location(name=unique_name("Деревня"), description="тест",
                        location_type=LocationType.SAFE)
        session.add(safe)
        await session.flush()
        user = User(telegram_id=unique_id(), username=unique_name("tg"))
        session.add(user)
        await session.flush()
        item = Item(name=unique_name("Меч"), description="тестовый",
                    item_type=ItemType.WEAPON, price=10, is_sellable=True)
        session.add(item)
        await session.flush()
        ch = Character(user_id=user.id, name=unique_name("Hoarder"),
                       character_class="warrior", level=7, stats_locked=True,
                       location_id=safe.id, bronze=25000)
        session.add(ch)
        await session.flush()
        bag = [InventoryItem(character_id=ch.id, item_id=item.id, quantity=1)
               for _ in range(3)]
        for b in bag:
            session.add(b)
        await session.flush()
        ids = [b.id for b in bag]

        mate_user = User(telegram_id=unique_id(), username=unique_name("m8"))
        session.add(mate_user)
        await session.flush()
        mate = Character(user_id=mate_user.id, name=unique_name("Mate"),
                         character_class="warrior", level=3,
                         stats_locked=True, location_id=safe.id)
        session.add(mate)
        await session.flush()
        mate_id = mate.id

        ok, msg = await core_home.settle(session, ch)
        assert ok, msg
        assert ch.house_level == 1 and ch.home_location_id == safe.id
        await session.commit()

    async with async_session() as session:
        ch = await session.get(Character, ch.id)
        first = await session.get(InventoryItem, ids[0])

        ok, msg = await core_home.put(session, ch, first)
        assert ok, msg
        assert first.in_home and not first.is_equipped

        # вместимость и «уже лежит»
        again = await core_home.put(session, ch, first)
        assert not again[0] and "уже" in again[1]

        st = await core_home.home_state(session, ch)
        assert st["count"] == 1 and st["capacity"] == 12
        assert st["at_home"] and st["next_cost"] == 6000

        # гибель: сундук не трогаем, сумка — да
        lost = await core_stash.drop_on_death(session, ch)
        assert all(li.id != first.id for li in lost)

        # подарок вещей из сундука запрещён (core/gifts)
        from core import gifts as core_gifts
        mate = await session.get(Character, mate_id)
        res = await core_gifts.gift_item(session, ch, mate, first, 1)
        assert not res["ok"] and "сундук" in res["reason"].lower(), res

        # надстройка
        ok, msg = await core_home.upgrade(session, ch)
        assert ok and ch.house_level == 2
        assert core_home.capacity_for(ch) == 24
        await session.commit()

    async with async_session() as session:
        ch = await session.get(Character, ch.id)
        first = await session.get(InventoryItem, ids[0])
        ok, msg = await core_home.take(session, ch, first)
        assert ok, msg
        assert not first.in_home
        assert ch.house_level == 2                 # всё пережито и сохранено
        await session.delete(first)
        await session.commit()


# ── подключение ────────────────────────────────────────────

def test_ui_wired():
    inv = open(os.path.join(ROOT, "bot/handlers/inventory.py")).read()
    for probe in ("home_buy", "home_up", "home_put:", "home_take:",
                  '"home": "🏠 Дом"', "in_home"):
        assert probe in inv, f"бот: нет {probe}"

    kb = open(os.path.join(ROOT, "bot/keyboards/inline.py")).read()
    assert "inv_sec:home:0" in kb and "Достать из сундука" in kb

    battle = open(os.path.join(ROOT, "bot/handlers/battle.py")).read()
    assert "rest_share_for" in battle                   # очаг в привале

    game = open(os.path.join(ROOT, "engine/game.py")).read()
    assert "homestead.button(self.store, p, rows)" in game
    assert "do_house = lambda" in game

    mods = json.load(open(os.path.join(ROOT, "modules.json")))["modules"]
    assert "engine/homestead.py" in mods
    html = open(os.path.join(ROOT, "index.html")).read()
    assert '"engine/homestead.py",' in html


def test_engine_purity():
    """Домашние правила не тянут ничего кроме движка."""
    tree = ast.parse(open(os.path.join(ROOT, "engine/homestead.py")).read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            imported.add((node.module or "").split(".")[0])
    foreign = imported - {"engine"}
    assert not foreign, f"engine/homestead.py импортирует чужое: {foreign}"
    lazy = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert all((n.module or "").startswith("engine") for n in lazy)
