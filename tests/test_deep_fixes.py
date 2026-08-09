import asyncio
import datetime
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import async_session
from core.models import User, Character, Location, Cell, Party, PartyInvite, DungeonRun, DungeonTemplate, Item, ItemInstance
from engine import currency, stats as engine_stats
from core import stats as core_stats
from core import auction as core_auction


class DummyPlayer:
    def __init__(self):
        self.bronze = None
        self.silver = None
        self.gold = None
        self.strength = None
        self.agility = None
        self.dexterity = None
        self.intelligence = None
        self.crit_chance = None
        self.crit_damage = None
        self.life_on_hit = None
        self.thorns_damage = None
        self.gear_score = None


def test_currency_none_attributes_safe():
    p = DummyPlayer()
    assert currency.total_in_bronze(p) == 0
    assert currency.currency_str(p) == "0🟤 0⚪ 0🟡"
    currency.normalize_currencies(p)
    assert p.bronze == 0 and p.silver == 0 and p.gold == 0

    currency.add_currency(p, bronze=150, silver=250, gold=1)
    # 150 bronze -> 1 silver, 50 bronze; silver was 250+1=251 -> 2 gold, 51 silver; gold was 1+2=3
    assert p.bronze == 50
    assert p.silver == 51
    assert p.gold == 3
    assert currency.total_in_bronze(p) == 35150

    # Large deduct returns False
    assert not currency.deduct_currency(p, 50000)
    assert currency.deduct_currency(p, 100)
    assert currency.total_in_bronze(p) == 35050


def test_calculate_gear_score_none_attributes_safe():
    p = DummyPlayer()
    gs = engine_stats.calculate_gear_score(p)
    assert gs == 0

    p.strength = 100
    p.crit_chance = 15
    gs2 = engine_stats.calculate_gear_score(p)
    assert gs2 == int(100 * 0.8) + int(15 * 2)  # 80 + 30 = 110


@pytest.mark.asyncio
async def test_core_combat_stats_none_attributes_safe():
    async with async_session() as session:
        user = User(telegram_id=999888777, username="stat_test")
        session.add(user)
        await session.flush()

        char = Character(
            user_id=user.id,
            name="NullStatHero",
            character_class="warrior",
            level=1,
            stats_locked=True,
        )
        session.add(char)
        await session.flush()

        # Manually force some stat attributes to None to test null-safety
        char.strength = None
        char.agility = None
        char.intelligence = None

        res = await core_stats.combat_stats(session, char)
        assert res["strength"] == 0
        assert res["agility"] == 0
        assert res["intelligence"] == 0
        assert res["max_hp"] >= 0
        assert res["damage"] == 0


@pytest.mark.asyncio
async def test_auction_suggested_price_safe():
    inst = ItemInstance(
        uid="IT-TEST001",
        item_id=1,
        quality=100,
        trade_count=None,
        is_one_of_a_kind=False,
        is_festive=False,
    )
    item = Item(
        id=1,
        name="Ржавый меч",
        price=None,
    )
    price = core_auction.suggested_price(inst, item)
    assert price >= 1
