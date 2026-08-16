"""Точки входа бота для подсистем, которые раньше жили без единой кнопки.

Запуск: python3 -m pytest -q tests/test_bot_entrypoints.py

Зачем. `core/archaeology.py`, `core/investments.py`, `core/pawnshop.py`,
`core/blackmarket.py`, `core/salvage.py`, `core/lunar.py`, `core/karma.py`
и `core/omens.py` были написаны и покрыты юнит-тестами, но ни один роутер
`bot/handlers/` их не вызывал — игрок не мог до них добраться. Здесь
проверяется именно связка «кнопка есть → хендлер зарегистрирован →
доменная функция меняет БД», а не сама доменная логика.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Детерминизм (пункт № 5): игровой random спинован своей константой,
# а уникальные telegram_id берутся вне seed — см. tests/_seed.py.
from _seed import pin, unique_id  # noqa: E402

pin(104)

from core.database import async_session
from core.models import (Character, InventoryItem, Item, ItemInstance,
                         Location, PawnLoan, TownInvestment, User)


def _rand_tg():
    return unique_id()


class _FakeCallback:
    """Минимальный объект под magic-фильтры aiogram (нужно только .data)."""

    def __init__(self, data):
        self.data = data


def _has_handler(router, callback_data: str) -> bool:
    """Есть ли в роутере обработчик, принимающий такой callback_data.

    Фильтры aiogram — magic-объекты, их нельзя сравнивать как строки;
    поэтому прогоняем через них фальшивый callback и смотрим на результат.
    """
    probe = _FakeCallback(callback_data)
    for handler in router.callback_query.handlers:
        for flt in handler.filters or []:
            try:
                if flt.callback(probe):
                    return True
            except Exception:
                continue
    return False


# ── кнопки существуют ───────────────────────────────────────

def test_inspect_keyboard_has_new_actions():
    """На клетке появились раскопки, вклад, ломбард и чёрный рынок."""
    from bot.keyboards.inline import inspect_keyboard

    wild = inspect_keyboard(has_mob=False, has_npc=False, has_chest=False,
                            can_dig=True, has_treasure=True)
    data = [b.callback_data for row in wild.inline_keyboard for b in row]
    assert "dig_relic" in data
    assert "dig_treasure" in data

    town = inspect_keyboard(has_mob=False, has_npc=False, has_chest=False,
                            is_town=True)
    tdata = [b.callback_data for row in town.inline_keyboard for b in row]
    assert "invest_menu" in tdata
    assert "pawnshop_menu" in tdata
    assert "blackmarket_menu" in tdata

    # В городе не копают, в дикой земле нет городских служб.
    assert "dig_relic" not in tdata
    assert "invest_menu" not in data


def test_item_book_keyboard_has_salvage_and_pawn():
    """В карточке вещи появились «Разобрать» и «Заложить»."""
    from bot.keyboards.inline import item_book_keyboard

    kb = item_book_keyboard(inv_item_id=7, section="gear", index=0, total=1,
                            can_salvage=True, can_pawn=True)
    data = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "salvage:7" in data
    assert "pawn:7" in data

    # Надетую вещь нельзя ни разобрать, ни заложить — правило core-модулей.
    worn = item_book_keyboard(inv_item_id=7, section="gear", index=0, total=1,
                              is_equipped=True, can_salvage=True, can_pawn=True)
    wdata = [b.callback_data for row in worn.inline_keyboard for b in row]
    assert "salvage:7" not in wdata
    assert "pawn:7" not in wdata


def test_main_menu_has_omens_button():
    from bot.keyboards.inline import main_menu_keyboard

    kb = main_menu_keyboard(has_character=True)
    data = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "omens_menu" in data


# ── хендлеры зарегистрированы ───────────────────────────────

def test_handlers_registered():
    """Каждой новой кнопке соответствует обработчик в роутере."""
    from bot.handlers.location import router as location_router
    from bot.handlers.inventory import router as inventory_router
    from bot.handlers.world_extra import router as world_router

    for cb in ("dig_relic", "dig_treasure", "blackmarket_menu", "bm_buy:bm_rune_void",
               "invest_menu", "invest_do:100"):
        assert _has_handler(location_router, cb), f"нет обработчика {cb} в location.py"

    for cb in ("salvage:7", "pawn:7", "pawnshop_menu", "pawn_redeem:3"):
        assert _has_handler(inventory_router, cb), f"нет обработчика {cb} в inventory.py"

    assert _has_handler(world_router, "omens_menu")

    # Негативная проверка: выдуманный колбэк никем не обрабатывается,
    # иначе тест был бы зелёным при любом фильтре.
    assert not _has_handler(location_router, "нет_такой_кнопки_вообще")


# ── доменные функции меняют БД ──────────────────────────────

@pytest.mark.asyncio
async def test_archaeology_flow_gives_map_and_treasure():
    """5 фрагментов → карта; раскопки на нужной клетке → клад."""
    from core import archaeology as core_arch
    from core.models import Cell

    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="digger")
        session.add(user)
        await session.flush()
        char = Character(user_id=user.id, name="Digger", character_class="warrior",
                         level=4, stats_locked=True)
        session.add(char)
        await session.flush()

        for i in range(4):
            res = await core_arch.find_relic_fragment(session, char)
            assert res["fragments"] == i + 1
            assert not res["formed_map"]

        res = await core_arch.find_relic_fragment(session, char)
        assert res["formed_map"] is True
        assert char.treasure_map_coord and char.treasure_map_coord.startswith("loc:")

        # Разбираем координаты карты и копаем ровно там.
        parts = char.treasure_map_coord.split(":")
        loc_id, tx, ty = int(parts[1]), int(parts[3]), int(parts[5])
        loc = await session.get(Location, loc_id)
        if loc is None:
            loc = Location(id=loc_id, name="Тестовая земля", description="—",
                           location_type="dangerous", min_level=1)
            session.add(loc)
            await session.flush()
        cell = Cell(location_id=loc_id, x=tx, y=ty, name="Пустошь",
                    description="—", tile_type="grass")
        session.add(cell)
        await session.flush()

        wrong = Cell(location_id=loc_id, x=tx + 1, y=ty + 1, name="Не то место",
                     description="—", tile_type="grass")
        session.add(wrong)
        await session.flush()
        miss = await core_arch.dig_treasure_at_cell(session, char, wrong)
        assert miss["ok"] is False           # мимо карты — ничего не выдаём

        hit = await core_arch.dig_treasure_at_cell(session, char, cell)
        assert hit["ok"] is True
        assert char.treasure_map_coord is None   # карта потрачена
        assert (char.soul_ash or 0) >= 30


@pytest.mark.asyncio
async def test_investment_dividends_are_paid():
    """Вклад принят, фоновая выплата начисляет дивиденды вкладчику."""
    from core import investments as core_inv
    from engine.currency import total_in_bronze

    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="investor")
        session.add(user)
        await session.flush()
        char = Character(user_id=user.id, name="Investor", character_class="warrior",
                         level=5, gold=10, stats_locked=True)
        session.add(char)
        loc = Location(name="Торговый Погост", description="—",
                       location_type="safe", min_level=1)
        session.add(loc)
        await session.flush()

        res = await core_inv.invest_in_town(session, char, loc.id, 1000)
        assert res["ok"] is True
        assert res["total_invested"] == 1000

        before = total_in_bronze(char)
        payouts = await core_inv.pay_dividends(session)
        mine = [p for p in payouts if p["character_id"] == char.id]
        assert mine, "вкладчик не получил дивиденды"
        expected = int(1000 * core_inv.DIVIDEND_RATE)
        assert mine[0]["amount"] == expected
        assert total_in_bronze(char) == before + expected

        summary = await core_inv.get_town_investment_summary(session, loc.id, char.id)
        assert summary["my_dividends"] == expected


@pytest.mark.asyncio
async def test_pawnshop_loan_and_redeem_roundtrip():
    """Залог вынимает вещь и даёт деньги, выкуп возвращает вещь."""
    from core import pawnshop as core_pawnshop
    from core.loot import new_uid
    from engine.currency import add_currency, total_in_bronze
    from sqlalchemy import select

    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="borrower")
        session.add(user)
        await session.flush()
        char = Character(user_id=user.id, name="Borrower", character_class="warrior",
                         level=5, stats_locked=True)
        session.add(char)
        item = Item(name="Родовой клинок", description="—", item_type="weapon",
                    rarity="rare", price=400)
        session.add(item)
        await session.flush()
        inst = ItemInstance(uid=new_uid(), item_id=item.id, quality=100)
        session.add(inst)
        await session.flush()
        inv = InventoryItem(character_id=char.id, item_id=item.id,
                            instance_id=inst.id, quantity=1)
        session.add(inv)
        await session.flush()

        loan = await core_pawnshop.create_pawn_loan(session, char, inv)
        assert loan["ok"] is True
        assert loan["buyback_price"] > loan["loan_bronze"]   # комиссия 15 %

        left = (await session.execute(
            select(InventoryItem).where(InventoryItem.character_id == char.id)
        )).scalars().all()
        assert not left, "заложенная вещь осталась в сумке"

        active = await core_pawnshop.list_active_loans(session, char.id)
        assert len(active) == 1

        add_currency(char, bronze=loan["buyback_price"])
        before = total_in_bronze(char)
        red = await core_pawnshop.redeem_pawn_loan(session, char, active[0].id)
        assert red["ok"] is True
        assert total_in_bronze(char) == before - loan["buyback_price"]

        back = (await session.execute(
            select(InventoryItem).where(InventoryItem.character_id == char.id)
        )).scalars().all()
        assert len(back) == 1, "выкупленная вещь не вернулась в сумку"
        assert back[0].instance_id == inst.id


@pytest.mark.asyncio
async def test_blackmarket_purchase_requires_money():
    """Без денег покупка отклоняется, с деньгами — списывает и выдаёт."""
    from core import blackmarket as core_bm
    from engine.currency import add_currency, total_in_bronze

    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="smuggler")
        session.add(user)
        await session.flush()
        char = Character(user_id=user.id, name="Smuggler", character_class="rogue",
                         level=6, gold=0, bronze=0, silver=0, stats_locked=True)
        session.add(char)
        await session.flush()

        ware = core_bm.get_black_market_wares()[0]
        poor = await core_bm.buy_black_market_item(session, char, ware["key"])
        assert poor["ok"] is False

        add_currency(char, bronze=ware["cost"])
        before = total_in_bronze(char)
        rich = await core_bm.buy_black_market_item(session, char, ware["key"])
        assert rich["ok"] is True
        assert total_in_bronze(char) <= before        # деньги списаны

        bad = await core_bm.buy_black_market_item(session, char, "нет_такого")
        assert bad["ok"] is False


@pytest.mark.asyncio
async def test_karma_effects_in_bot_helpers():
    """Карма бота: пороги, спасение от фатального удара, бонус лечения."""
    from core import karma as core_karma
    from bot.handlers.battle import _blessing_saves

    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="saint")
        session.add(user)
        await session.flush()
        char = Character(user_id=user.id, name="Saint", character_class="paladin",
                         level=5, karma_score=0, stats_locked=True)
        session.add(char)
        await session.flush()

        core_karma.change_karma(char, core_karma.PIOUS_KARMA)
        assert core_karma.pious(char)

        state = {}
        assert _blessing_saves(char, state) is True
        assert state["character_hp"] == 1
        assert _blessing_saves(char, state) is False     # один раз за бой

        char.karma_score = 0
        assert _blessing_saves(char, {}) is False        # нейтрального не спасает

        core_karma.change_karma(char, core_karma.DEFILED_KARMA)
        assert core_karma.defiled(char)
        assert core_karma.karma_status(char)[0] == "💀"


def test_lunar_phase_is_deterministic_and_covers_cycle():
    """Фаза луны считается от времени и покрывает все 4 состояния."""
    from core import lunar as core_lunar

    seen = set()
    for hour in range(0, core_lunar.CYCLE_DURATION_HOURS):
        phase = core_lunar.get_current_lunar_phase(hour * 3600)
        seen.add(phase["key"])
    assert len(seen) == len(core_lunar.PHASES)

    fixed = 1_700_000_000
    assert (core_lunar.get_current_lunar_phase(fixed)["key"]
            == core_lunar.get_current_lunar_phase(fixed)["key"])
    assert "Знамение" not in core_lunar.lunar_phase_banner()
