"""Осады замков: правила, поток обоих стеков, паритет (IDEAS-next, пункт 4).

Запуск: python3 -m pytest -q tests/test_siege_parity.py

Зачем. Осада была декорацией: событие рисовало HP ворот, но повлиять на
них мог лишь админ, снявший событие, а браузерный стек про осаду вообще не
знал. Здесь закрепляем:

* правила (роли, роллы, падение, клампы репутации) — чистые функции
  `engine/siege.py`, общие для обоих стеков;
* серверный поток: удары копятся в БД, замок падает, веха попадает в
  Летопись, повторная осада занятого замка невозможна;
* браузерный поток: то же самое на store (тот же RULES-объект, те же
  исходы);
* подключение: кнопки бота имеют обработчики, панель умеет начинать/снимать
  осады, модуль прописан в манифесте браузера.
"""
import json
import os
import random
import sys
import time

import pytest
from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _seed import pin, unique_id, unique_name  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

pin(933)

from engine import siege

CASTLE_NAME = "Замок Рассвета"          # владелец по CASTLE_OWNERS — order


# ── чистые правила ─────────────────────────────────────────

def test_roles_are_allegiance_based():
    assert siege.role_for("cult", "cult") == "assault"
    assert siege.role_for("order", "cult") == "defend"
    assert siege.role_for(None, "cult") == "defend"      # бесфракционный — на стене
    assert siege.role_for("guard", "cult") == "defend"   # союзник врага тоже


def test_roll_grows_with_level_and_jitters():
    rng = random.Random(7)
    weak = sum(siege.strike_roll("assault", 1, rng) for _ in range(40)) / 40
    strong = sum(siege.strike_roll("assault", 30, rng) for _ in range(40)) / 40
    assert strong > weak > 0
    base = siege.RULES["assault_base"] + siege.RULES["assault_per_level"]
    rolls = [siege.strike_roll("assault", 1, rng) for _ in range(30)]
    assert all(0.8 * base - 1 <= r <= 1.2 * base for r in rolls)   # ±20 %


def test_gates_fall_once_and_repair_is_capped():
    hp, outcome = siege.apply_roll(50, 3000, "assault", 100)
    assert (hp, outcome) == (0, "captured")
    hp, outcome = siege.apply_roll(2990, 3000, "defend", 500)
    assert (hp, outcome) == (3000, "progress")   # выше максимума не растёт


def test_reputation_clamps():
    rep = {}
    siege.bump_side(rep, "guard", 10 ** 6)
    assert rep["guard"] == 300
    siege.bump_side(rep, "guard", -10 ** 6)
    assert rep["guard"] == -200


def test_server_rules_are_the_same_object():
    """Единый источник чисел: сервер не хранит копию, а импортирует."""
    from core import worldevents as we
    assert we.SIEGE_RULES is siege.RULES


# ── браузерный поток (store) ───────────────────────────────

def _store():
    """Тот же браузерный стор, что и в остальных движковых тестах."""
    from engine.storage import Store
    from webapp.backend import MemoryStorage
    store = Store(MemoryStorage())
    store.settings["siege_auto"] = False      # автоосады не мешают тестам
    return store


def _hero(name, faction, level=10, loc=0):
    from engine.models import Player
    p = Player(tg_id=unique_id(), name=name, level=level)
    p.reputation = {faction: 100}
    p.loc = loc
    return p


def test_engine_siege_flow_assault_defend_capture():
    st = _store()
    castle = siege.castles_idx()[0]              # Замок Рассвета → order
    ev = siege.start(st, "cult", castle)
    assert ev["hp"] == siege.RULES["hp"]
    with pytest.raises(ValueError):
        siege.start(st, "cult", castle)          # уже осаждают

    defender = _hero(unique_name("Wall"), "order", loc=castle)
    r = siege.hit(st, defender)
    assert r["ok"] and r["role"] == "defend"
    assert r["hp"] == siege.RULES["hp"]          # чинить уже целое — поздно

    second = siege.hit(st, defender)             # кулдаун
    assert not second["ok"] and "Отдышись" in second["reason"]

    attacker = _hero(unique_name("Ram"), "cult", level=25, loc=castle)
    now = time.time()
    outcome, hits = "progress", 0
    while outcome != "captured" and hits < 200:
        now += siege.RULES["cooldown"] + 1
        res = siege.hit(st, attacker, rng=random.Random(hits), now=now)
        assert res["ok"], res
        outcome = res["outcome"]
        hits += 1
    assert outcome == "captured" and hits >= 5
    assert siege.active(st, castle) == []        # осада закончилась
    assert attacker.bronze > 50                  # награда бронзой (старт 50)
    assert attacker.reputation["cult"] > 100     # и репутацией своей стороне


def test_engine_auto_starts_only_on_rival_castle():
    """auto() — на каждом взгляде на клетку; тут ручной rng-детерминизм."""
    class _Rng:
        def random(self):
            return 0.0

        def choice(self, seq):
            return list(seq)[0]

    st = _store()
    st.settings["siege_auto"] = True
    # choice FACTIONS -> "guard", castles[0] -> Замок Рассвета (order): не себя
    ev = siege.auto(st, rng=_Rng())
    assert ev is not None and ev["attacker"] == "guard"
    assert siege.auto(st, rng=_Rng()) is None    # одна война — уже громко


# ── серверный поток (БД) ───────────────────────────────────

@pytest.mark.asyncio
async def test_server_siege_lifecycle_and_legend():
    from core import factions as cf
    from core import worldevents as we
    from core.database import async_session
    from core.models import (Character, Location, ServerRecord, User,
                             WorldEvent)

    async with async_session() as session:
        loc = Location(name=f"{CASTLE_NAME} {unique_id()}", description="тест")
        session.add(loc)
        await session.flush()

        async def _mk(faction):
            user = User(telegram_id=unique_id(), username=unique_name("tg"))
            session.add(user)
            await session.flush()
            ch = Character(user_id=user.id, name=unique_name("Siege"),
                           character_class="warrior", level=15,
                           stats_locked=True, location_id=loc.id,
                           bronze=100)
            session.add(ch)
            cf.save(ch, {faction: 100})
            await session.flush()
            return ch

        assaulter = await _mk("cult")          # осаждает
        keeper = await _mk("order")            # держит стену

        ev = await we.siege_begin(session, loc.id, "cult")
        assert ev.key == "siege_cult" and ev.hp == we.SIEGE_RULES["hp"]
        with pytest.raises(ValueError):
            await we.siege_begin(session, loc.id, "cult")
        await session.commit()

    async with async_session() as session:
        assaulter = await session.get(Character, assaulter.id)
        keeper = await session.get(Character, keeper.id)

        # защитник: роль defend, ремонт не превышает максимум
        we._siege_cd.clear()
        r = await we.siege_hit(session, keeper)
        assert r["ok"] and r["role"] == "defend"
        assert r["hp"] <= r["max_hp"]

        # кулдаун
        r2 = await we.siege_hit(session, keeper)
        assert not r2["ok"] and "Отдышись" in r2["reason"]

        # штурм до падения
        we._siege_cd.clear()
        outcome, hits = "progress", 0
        while outcome != "captured" and hits < 300:
            we._siege_cd.clear()
            r = await we.siege_hit(session, assaulter)
            assert r["ok"], r
            outcome = r["outcome"]
            hits += 1
        assert outcome == "captured"
        await session.commit()

    async with async_session() as session:
        ev = await session.get(WorldEvent, ev.id)
        assert not ev.is_active
        assaulter = await session.get(Character, assaulter.id)
        from engine.currency import total_in_bronze
        # награда бронзой, но engine/currency нормализует: считаем всё в бронзе
        assert total_in_bronze(assaulter) > 100
        assert cf.value(assaulter, "cult") > 100

        row = (await session.execute(
            select(ServerRecord)
            .where(ServerRecord.record_key == f"siege-capture:{loc.id}")
        )).scalars().first()
        assert row is not None, "падение замка — событие Летописи"
        assert row.holder_character_name == assaulter.name

        # осада закончилась: состояние больше ничего не показывает
        st = await we.siege_state(session, assaulter)
        assert not st["ok"]

        # чистим веху, чтобы повторный прогон теста остался детерминированным
        await session.delete(row)
        await session.commit()


# ── подключение ко всем витринам ───────────────────────────

def test_ui_wired_everywhere():
    """Осада видна там, где в неё играют: бот, браузер, админка."""
    bot = open(os.path.join(ROOT, "bot/handlers/location.py")).read()
    assert 'F.data == "siege_menu"' in bot            # экран на клетке
    assert 'F.data == "siege_hit"' in bot              # удар/починка

    game = open(os.path.join(ROOT, "engine/game.py")).read()
    assert "siege" in game and "do_siege" in game      # роутер браузера
    screen = open(os.path.join(ROOT, "engine/siege.py")).read()
    assert "def screen" in screen and "def button" in screen

    admin = open(os.path.join(ROOT, "admin/main.py")).read()
    assert '"/editor/living/siege"' in admin
    assert "/editor/living/siege/{event_id}/end" in admin
    tpl = open(os.path.join(ROOT, "admin/templates/editor_living.html")).read()
    assert "Начать осаду" in tpl and "Осады замков" in tpl

    mods = json.load(open(os.path.join(ROOT, "modules.json")))["modules"]
    assert "engine/siege.py" in mods                   # бандл подхватит
    fallback = open(os.path.join(ROOT, "index.html")).read()
    assert '"engine/siege.py"' in fallback              # и аварийный список
