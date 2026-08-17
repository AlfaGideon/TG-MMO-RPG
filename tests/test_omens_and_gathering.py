import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Детерминизм (пункт № 5): игровой random спинован своей константой,
# а уникальные telegram_id берутся вне seed — см. tests/_seed.py.
from _seed import pin, unique_id  # noqa: E402

pin(113)

from core.database import async_session
from core.models import User, Character, Location, Cell, Grave, Mob, MobSpawn
from core import omens as core_omens
from core import spectral as core_spectral
from core import bounty as core_bounty
from core import gathering as core_gathering


def _rand_tg():
    return unique_id()


def test_omens_and_harbingers():
    omens = core_omens.get_current_omens()
    assert len(omens) >= 3
    banner = core_omens.omen_banner()
    assert "Знамение" in banner


@pytest.mark.asyncio
async def test_spectral_nomad_and_soul_ash():
    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="ghost_friend")
        session.add(user)
        await session.flush()

        char = Character(
            user_id=user.id,
            name="SpiritWalker",
            character_class="mage",
            level=3,
            max_mp=40,
            current_mp=20,
            soul_ash=0,
            stats_locked=True,
        )
        session.add(char)
        await session.flush()

        grave = Grave(character_id=char.id, location_id=1, x=3, y=3, gold=100)
        session.add(grave)
        await session.flush()

        # Harvest soul ash
        harv = await core_spectral.harvest_soul_ash(session, char, grave)
        assert harv["ok"]
        assert harv["gained"] == 25
        assert char.soul_ash == 25

        # Give enough ash to buy ancestor tear
        char.soul_ash = 100
        buy_res = await core_spectral.buy_spectral_item(session, char, "spec_ancestor_tear")
        assert buy_res["ok"]
        assert char.max_mp == 50  # 40 + 10
        assert char.soul_ash == 50


@pytest.mark.asyncio
async def test_bounty_hunting_slayers():
    async with async_session() as session:
        loc = Location(name="Гиблое болото", description="Болото", grid_size=10, min_level=1)
        session.add(loc)
        await session.flush()

        mob = Mob(name="Болотный тролль", description="Грозный тролль", location_id=loc.id, hp=100, damage=15, exp_reward=50, gold_reward=20)
        session.add(mob)
        await session.flush()

        spawn = MobSpawn(mob_id=mob.id, home_location_id=loc.id, location_id=loc.id, is_alive=True)
        session.add(spawn)
        await session.flush()

        # Record kills
        await core_bounty.record_mob_kill(session, spawn)
        await core_bounty.record_mob_kill(session, spawn)
        assert spawn.kill_count == 2
        assert spawn.bounty_title is not None

        reward = core_bounty.calculate_bounty_reward(spawn)
        assert reward == 150 + 2 * 100  # 350


@pytest.mark.asyncio
async def test_fishing_and_herbalism():
    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="angler")
        session.add(user)
        await session.flush()

        char = Character(
            user_id=user.id,
            name="OldFisherman",
            character_class="warrior",
            level=2,
            current_hp=20,
            max_hp=100,
            stats_locked=True,
        )
        session.add(char)
        await session.flush()

        # Fishing
        fish_res = await core_gathering.fish_on_water(session, char)
        assert fish_res["ok"]
        assert "Рыбалка" in fish_res["title"]

        # Herbalism
        herb_res = await core_gathering.gather_herbs(session, char)
        assert herb_res["ok"]
        assert "Травничество" in herb_res["title"]
        assert char.experience >= 20
