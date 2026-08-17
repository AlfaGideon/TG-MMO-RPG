import os
import sys
import pytest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Детерминизм (пункт № 5): игровой random спинован своей константой,
# а уникальные telegram_id берутся вне seed — см. tests/_seed.py.
from _seed import pin, unique_id  # noqa: E402

pin(109)

from core.database import async_session
from core.models import User, Character, Location, Cell, FactionOutpost, FactionDecree, WorldEvent
from core import factions as core_factions
from core import worldevents as core_worldevents
from core import stats as core_stats


def _rand_tg():
    return unique_id()


@pytest.mark.asyncio
async def test_faction_outpost_capture_and_bonuses():
    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="outpost_tester")
        session.add(user)
        await session.flush()

        loc = Location(name="Северный тракт", description="Северный тракт", grid_size=10, min_level=1)
        session.add(loc)
        await session.flush()

        cell = Cell(location_id=loc.id, x=2, y=2, name="Сторожевая вышка", description="Вышка", is_passable=True)
        session.add(cell)
        await session.flush()

        char = Character(
            user_id=user.id,
            name="Commander",
            character_class="warrior",
            level=5,
            strength=25,
            faction="guard",
            reputation='{"guard": 100, "scavengers": 0, "cult": 0, "order": 0}',
            stats_locked=True,
        )
        session.add(char)
        await session.flush()

        outpost = FactionOutpost(
            name="Аванпост Севера",
            location_id=loc.id,
            cell_id=cell.id,
            controlling_faction="cult",
            defense_hp=50,
            max_defense_hp=500,
        )
        session.add(outpost)
        await session.commit()

        # Attack outpost
        res = await core_factions.attack_outpost(session, char, outpost, damage=60)
        assert res["ok"]
        assert res["captured"]
        assert outpost.controlling_faction == "guard"
        assert outpost.defense_hp == 250

        # Repair own outpost
        rep_res = await core_factions.attack_outpost(session, char, outpost, damage=50)
        assert rep_res["ok"]
        assert rep_res.get("repaired")
        assert outpost.defense_hp == 300

        # Bonus verification
        bonuses = await core_factions.faction_outpost_bonuses(session, "guard")
        assert bonuses["outposts_count"] >= 1
        assert bonuses["damage_pct"] >= 5


@pytest.mark.asyncio
async def test_castle_siege_event():
    async with async_session() as session:
        loc = Location(name="Замок Рассвета", description="Замок Рассвета", grid_size=25, min_level=1)
        session.add(loc)
        await session.flush()

        siege = await core_worldevents.start_siege(session, loc.id, attacking_faction="cult", hp=1000, hours=2.0)
        assert siege.is_active
        assert siege.hp == 1000

        active = await core_worldevents.active_sieges(session, loc.id)
        assert len(active) >= 1


@pytest.mark.asyncio
async def test_tunnel_sabotage_actions():
    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="saboteur")
        session.add(user)
        await session.flush()

        char = Character(
            user_id=user.id,
            name="ShadowBlade",
            character_class="rogue",
            level=4,
            faction="scavengers",
            reputation='{"guard": 0, "scavengers": 150, "cult": 0, "order": 0}',
            stats_locked=True,
        )
        session.add(char)
        await session.flush()

        res1 = await core_factions.sabotage_tunnel(session, char, 2, "poison_supplies")
        assert res1["ok"]
        assert "Яд в колодцах" in res1["title"]

        res2 = await core_factions.sabotage_tunnel(session, char, 2, "scout_alarm")
        assert res2["ok"]

        res3 = await core_factions.sabotage_tunnel(session, char, 2, "disrupt_forge")
        assert res3["ok"]


@pytest.mark.asyncio
async def test_caravan_escort_and_ambush():
    async with async_session() as session:
        user1 = User(telegram_id=_rand_tg(), username="guard_hero")
        user2 = User(telegram_id=_rand_tg(), username="cult_hero")
        session.add_all([user1, user2])
        await session.flush()

        loc = Location(name="Тракт Купцов", description="Тракт Купцов", grid_size=10, min_level=1)
        session.add(loc)
        await session.flush()

        c_guard = Character(
            user_id=user1.id, name="SirGalahad", character_class="paladin",
            level=3, faction="guard", reputation='{"guard": 100}', stats_locked=True,
        )
        c_cult = Character(
            user_id=user2.id, name="DarkAcolyte", character_class="mage",
            level=3, faction="cult", reputation='{"cult": 100}', stats_locked=True,
        )
        session.add_all([c_guard, c_cult])
        await session.flush()

        caravan_ev = await core_worldevents.spawn_caravan(session, loc.id, hours=4.0)
        assert caravan_ev.is_active

        # Escort
        esc_res = await core_factions.caravan_action(session, c_guard, caravan_ev, "escort")
        assert esc_res["ok"]
        assert "сопровождён" in esc_res["title"]

        # Ambush
        amb_res = await core_factions.caravan_action(session, c_cult, caravan_ev, "ambush")
        assert amb_res["ok"]
        assert "разграблен" in amb_res["title"]


@pytest.mark.asyncio
async def test_faction_treasury_and_decrees():
    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="leader_user")
        session.add(user)
        await session.flush()

        char = Character(
            user_id=user.id,
            name="GuildMaster",
            character_class="warrior",
            level=10,
            gold=20, # 20 gold = 200,000 bronze
            bronze=0,
            silver=0,
            faction="order",
            reputation='{"order": 350, "guard": 0, "scavengers": 0, "cult": 0}',
            stats_locked=True,
        )
        session.add(char)
        await session.flush()

        # Donate to treasury
        don_res = await core_factions.donate_treasury(session, char, "order", 3000)
        assert don_res["ok"]
        assert don_res["treasury"] >= 3000

        # Enact decree
        dec_res = await core_factions.enact_decree(session, char, "order", "militarization", hours=12)
        assert dec_res["ok"]
        assert "Милитаризация" in dec_res["decree"]

        # Check bonuses
        b = await core_factions.active_decree_bonuses(session, "order")
        assert b["damage_mult"] == 1.15

        # Combat stats integration
        cstats = await core_stats.combat_stats(session, char)
        assert cstats["damage_mult"] >= 1.15
        dmg = core_stats.attack_power(cstats, char)
        assert dmg > 10
