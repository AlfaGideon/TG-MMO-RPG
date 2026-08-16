import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Детерминизм (пункт № 5): игровой random спинован своей константой,
# а уникальные telegram_id берутся вне seed — см. tests/_seed.py.
from _seed import pin, unique_id  # noqa: E402

pin(107)

from core.database import async_session
from core.models import User, Character, Location, Cell, DungeonRun, DungeonCell, CharacterShadow
from core import familiars as core_familiars
from core import arena as core_arena
from core import dungeons as core_dungeons


def _rand_tg():
    return unique_id()


@pytest.mark.asyncio
async def test_familiar_adoption_and_bonuses():
    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="pet_master")
        session.add(user)
        await session.flush()

        char = Character(
            user_id=user.id,
            name="BeastLord",
            character_class="ranger",
            level=3,
            gold=10,
            stats_locked=True,
        )
        session.add(char)
        await session.flush()

        # Set familiar
        ok = core_familiars.set_familiar(char, "crow", "Каркуша")
        assert ok
        fam = core_familiars.get_familiar(char)
        assert fam["custom_name"] == "Каркуша"
        assert fam["type"] == "crow"

        bonuses = core_familiars.familiar_bonuses(char)
        assert bonuses["gold_to_stash_pct"] == 50
        assert bonuses["crit_bonus"] >= 5.0

        card = core_familiars.familiar_card_text(char)
        assert "Каркуша" in card


@pytest.mark.asyncio
async def test_shadow_arena_and_duels():
    async with async_session() as session:
        u1 = User(telegram_id=_rand_tg(), username="gladiator1")
        u2 = User(telegram_id=_rand_tg(), username="gladiator2")
        session.add_all([u1, u2])
        await session.flush()

        c1 = Character(user_id=u1.id, name="Achilles", character_class="warrior", level=8, strength=30, stats_locked=True)
        c2 = Character(user_id=u2.id, name="Hector", character_class="paladin", level=7, strength=25, stats_locked=True)
        session.add_all([c1, c2])
        await session.flush()

        shadow1 = await core_arena.update_character_shadow(session, c1)
        shadow2 = await core_arena.update_character_shadow(session, c2)
        await session.commit()

        opponents = await core_arena.get_shadow_opponents(session, c1)
        assert len(opponents) >= 1
        assert any(o.name == "Hector" for o in opponents)

        # Duel
        duel_res = await core_arena.duel_shadow(session, c1, shadow2)
        assert "victory" in duel_res
        assert duel_res["rounds"] >= 1
        assert duel_res["tokens"] > 0
        assert c1.gladiator_tokens >= duel_res["tokens"]


def test_dungeon_affixes():
    affs = core_dungeons.roll_affixes(2)
    assert len(affs) == 2
    for a in affs:
        assert a in core_dungeons.DUNGEON_AFFIXES
        assert "name" in core_dungeons.DUNGEON_AFFIXES[a]


@pytest.mark.asyncio
async def test_corrupted_altars_mechanic():
    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="altar_user")
        session.add(user)
        await session.flush()

        char = Character(
            user_id=user.id,
            name="AbyssSeeker",
            character_class="mage",
            level=4,
            current_hp=10,
            max_hp=100,
            current_mp=5,
            max_mp=50,
            gold=5,
            stats_locked=True,
        )
        session.add(char)
        await session.flush()

        run = DungeonRun(character_id=char.id, seed=123, floor=1, is_active=True)
        session.add(run)
        await session.flush()

        # Blood Altar
        res_blood = await core_dungeons.use_corrupted_altar(session, char, run, "blood")
        assert res_blood["ok"]
        assert char.current_hp == 100
        assert char.current_mp == 50

        # Abyssal Altar
        res_abyss = await core_dungeons.use_corrupted_altar(session, char, run, "abyssal")
        assert res_abyss["ok"]
        assert run.altar_boon == "abyssal_strength"
