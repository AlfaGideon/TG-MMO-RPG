import os
import random
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import async_session
from core.models import User, Character
from core import subclasses as core_subclasses
from core import talents as core_talents
from core import karma as core_karma
from core import titles as core_titles
from core import prestige as core_prestige
from core import stats as core_stats


def _rand_tg():
    return random.randint(100_000_000, 999_999_999)


@pytest.mark.asyncio
async def test_subclass_ascendancy_choice():
    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="subclass_hero")
        session.add(user)
        await session.flush()

        char = Character(user_id=user.id, name="Conan", character_class="warrior", level=10, stats_locked=True)
        session.add(char)
        await session.flush()

        subs = core_subclasses.get_available_subclasses("warrior")
        assert len(subs) >= 2
        assert any(s["key"] == "berserker" for s in subs)

        # Choose Berserker
        res = core_subclasses.choose_subclass(char, "berserker")
        assert res["ok"]
        assert char.subclass == "berserker"

        bonuses = core_subclasses.subclass_bonuses(char)
        assert bonuses["damage_mult"] == 1.25


@pytest.mark.asyncio
async def test_passive_constellations_and_talents():
    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="star_hero")
        session.add(user)
        await session.flush()

        char = Character(
            user_id=user.id, name="StarSeeker", character_class="mage",
            level=6, talent_points=2, max_hp=100, max_mp=50, stats_locked=True,
        )
        session.add(char)
        await session.flush()

        # Unlock Star of Fortitude
        t_res1 = core_talents.unlock_talent(char, "star_fortitude")
        assert t_res1["ok"]
        assert char.talent_points == 1
        assert char.max_hp == 150

        # Unlock Star of Wrath
        t_res2 = core_talents.unlock_talent(char, "star_wrath")
        assert t_res2["ok"]
        assert char.talent_points == 0

        t_bonuses = core_talents.talent_bonuses(char)
        assert t_bonuses["damage"] == 15
        assert t_bonuses["defense"] == 10


def test_karma_and_sin_system():
    char = Character(name="KarmaKnight", karma_score=0)
    # Neutral
    _, title_n, _ = core_karma.karma_status(char)
    assert "Нейтральный" in title_n

    # Good deeds
    core_karma.change_karma(char, +200)
    icon_g, title_g, _ = core_karma.karma_status(char)
    assert "Благочестивый" in title_g

    # Sins
    core_karma.change_karma(char, -450)
    icon_s, title_s, _ = core_karma.karma_status(char)
    assert "Осквернитель" in title_s


def test_titles_and_feats():
    char = Character(name="TitleHero")
    # Unlock title
    ok = core_titles.unlock_title(char, "Убийца Левиафана")
    assert ok
    titles = core_titles.get_unlocked_titles(char)
    assert "Убийца Левиафана" in titles

    # Set active title
    set_ok = core_titles.set_active_title(char, "Убийца Левиафана")
    assert set_ok
    assert char.active_title == "Убийца Левиафана"

    b = core_titles.title_bonus(char)
    assert b["damage"] == 5


@pytest.mark.asyncio
async def test_prestige_and_rebirth():
    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="veteran_rebirth")
        session.add(user)
        await session.flush()

        char = Character(
            user_id=user.id, name="AncientGod", character_class="warrior",
            level=15, strength=50, max_hp=300, stats_locked=True,
        )
        session.add(char)
        await session.flush()

        can_rb, _ = core_prestige.can_rebirth(char)
        assert can_rb

        rb_res = await core_prestige.perform_rebirth(session, char)
        assert rb_res["ok"]
        assert char.rebirth_count == 1
        assert char.level == 1
        assert char.strength == int(50 * 1.10)  # 55
        assert char.max_hp == int(300 * 1.10)   # 330
