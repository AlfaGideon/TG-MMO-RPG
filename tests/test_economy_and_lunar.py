import os
import random
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import async_session
from core.models import User, Character, Location, Item, ItemInstance, InventoryItem, PawnLoan, TownInvestment
from core import salvage as core_salvage
from core import investments as core_investments
from core import pawnshop as core_pawnshop
from core import blackmarket as core_blackmarket
from core import lunar as core_lunar


def _rand_tg():
    return random.randint(100_000_000, 999_999_999)


@pytest.mark.asyncio
async def test_salvaging_equipment():
    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="salvager")
        session.add(user)
        await session.flush()

        char = Character(user_id=user.id, name="ScrapHero", character_class="warrior", level=3, stats_locked=True)
        session.add(char)
        await session.flush()

        item = Item(name="Стальной топор", description="Острый топор", item_type="weapon", rarity="rare", price=200)
        session.add(item)
        await session.flush()

        from core.loot import new_uid
        inst = ItemInstance(uid=new_uid(), item_id=item.id, quality=100, upgrade_level=2)
        session.add(inst)
        await session.flush()

        inv = InventoryItem(character_id=char.id, item_id=item.id, instance_id=inst.id, quantity=1)
        session.add(inv)
        await session.commit()

        # Salvage item
        res = await core_salvage.salvage_item(session, char, inv)
        assert res["ok"]
        assert res["materials"]["iron_scrap"] >= 8

        # Check that original item is destroyed
        inst_check = await session.get(ItemInstance, inst.id)
        assert inst_check is None


@pytest.mark.asyncio
async def test_town_investments_and_dividends():
    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="investor")
        session.add(user)
        await session.flush()

        char = Character(user_id=user.id, name="MerchantBaron", character_class="warrior", level=5, gold=20, stats_locked=True)
        session.add(char)
        await session.flush()

        loc = Location(name="Погост Костров", description="Безопасная деревня", grid_size=10, min_level=1)
        session.add(loc)
        await session.flush()

        # Invest 5000 bronze
        inv_res = await core_investments.invest_in_town(session, char, loc.id, bronze_amount=5000)
        assert inv_res["ok"]
        assert inv_res["invested"] == 5000

        summary = await core_investments.get_town_investment_summary(session, loc.id, char.id)
        assert summary["my_invested"] == 5000
        assert summary["share_pct"] == 100


@pytest.mark.asyncio
async def test_pawn_loans_and_redemption():
    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="pawn_user")
        session.add(user)
        await session.flush()

        char = Character(user_id=user.id, name="DesperateKnight", character_class="warrior", level=3, gold=5, stats_locked=True)
        session.add(char)
        await session.flush()

        item = Item(name="Древний меч", description="Клинок", item_type="weapon", price=300)
        session.add(item)
        await session.flush()

        from core.loot import new_uid
        inst = ItemInstance(uid=new_uid(), item_id=item.id, quality=100)
        session.add(inst)
        await session.flush()

        inv = InventoryItem(character_id=char.id, item_id=item.id, instance_id=inst.id, quantity=1)
        session.add(inv)
        await session.commit()

        # Pawn item
        loan_res = await core_pawnshop.create_pawn_loan(session, char, inv, days=3)
        assert loan_res["ok"]
        assert loan_res["loan_bronze"] > 0
        loan_bronze = loan_res["loan_bronze"]

        active_loans = await core_pawnshop.list_active_loans(session, char.id)
        assert len(active_loans) == 1
        loan = active_loans[0]

        # Redeem item
        red_res = await core_pawnshop.redeem_pawn_loan(session, char, loan.id)
        assert red_res["ok"]

        active_loans_after = await core_pawnshop.list_active_loans(session, char.id)
        assert len(active_loans_after) == 0


@pytest.mark.asyncio
async def test_black_market_wares():
    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="bm_buyer")
        session.add(user)
        await session.flush()

        char = Character(user_id=user.id, name="ShadowBuyer", character_class="rogue", level=4, gold=10, stats_locked=True)
        session.add(char)
        await session.flush()

        wares = core_blackmarket.get_black_market_wares()
        assert len(wares) >= 3

        buy_res = await core_blackmarket.buy_black_market_item(session, char, "bm_contraband_chest")
        assert buy_res["ok"]
        assert "открыл" in buy_res["desc"]


def test_lunar_cycles():
    # 4 distinct phases
    phases = [p["key"] for p in core_lunar.PHASES]
    assert "full_moon" in phases
    assert "new_moon" in phases
    assert "waxing_moon" in phases
    assert "waning_moon" in phases

    cur = core_lunar.get_current_lunar_phase()
    assert cur["key"] in phases
    assert "desc" in cur

    banner = core_lunar.lunar_phase_banner()
    assert len(banner) > 5
