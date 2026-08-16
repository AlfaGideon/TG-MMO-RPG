import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Детерминизм (пункт № 5): игровой random спинован своей константой,
# а уникальные telegram_id берутся вне seed — см. tests/_seed.py.
from _seed import pin, unique_id  # noqa: E402

pin(112)

from core.database import async_session
from core.models import User, Character, Location, Cell, ServerRecord
from core import bestiary as core_bestiary
from core import archaeology as core_archaeology
from core import illusions as core_illusions
from core import legends as core_legends
from core import dialogue as core_dialogue


def _rand_tg():
    return unique_id()


@pytest.mark.asyncio
async def test_monster_bestiary_progress():
    char = Character(name="MonsterHunter", bestiary_kills_json="{}")

    # Record kills
    for _ in range(35):
        core_bestiary.record_kill(char, "Пещерный паук")

    b = core_bestiary.get_bestiary(char)
    assert b["Пещерный паук"] == 35

    bonus = core_bestiary.get_mob_slayer_bonus(char, "Пещерный паук")
    assert bonus == 1.03  # 35 // 10 = 3% bonus -> 1.03

    card = core_bestiary.bestiary_card_text(char)
    assert "Пещерный паук" in card


@pytest.mark.asyncio
async def test_relic_archaeology_and_treasure_map():
    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="archaeologist")
        session.add(user)
        await session.flush()

        char = Character(user_id=user.id, name="IndianaJones", character_class="ranger", level=4, relic_fragments=4, stats_locked=True)
        session.add(char)
        await session.flush()

        # Find 5th fragment -> forms map
        f_res = await core_archaeology.find_relic_fragment(session, char)
        assert f_res["ok"]
        assert f_res["formed_map"]
        assert char.treasure_map_coord is not None

        # Parse map coordinates
        parts = char.treasure_map_coord.split(":")
        loc_id, tx, ty = int(parts[1]), int(parts[3]), int(parts[5])

        loc = Location(name="Забытые Руины", description="Руины", grid_size=10, min_level=1)
        session.add(loc)
        await session.flush()

        cell = Cell(location_id=loc_id, x=tx, y=ty, name="Тайное место", is_passable=True)
        session.add(cell)
        await session.flush()

        # Dig treasure
        dig_res = await core_archaeology.dig_treasure_at_cell(session, char, cell)
        assert dig_res["ok"]
        assert "РАСКОПАН" in dig_res["title"]
        assert char.soul_ash >= 30


@pytest.mark.asyncio
async def test_illusory_wall_dispelling():
    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="illusion_seeker")
        session.add(user)
        await session.flush()

        char = Character(user_id=user.id, name="TrueSight", character_class="mage", level=5, stats_locked=True)
        session.add(char)
        await session.flush()

        loc = Location(name="Замок Теней", description="Замок", grid_size=10, min_level=1)
        session.add(loc)
        await session.flush()

        wall_cell = Cell(
            location_id=loc.id, x=4, y=4, name="Фальшивая стена",
            is_passable=False, is_illusory_wall=True, tile_type="wall",
        )
        session.add(wall_cell)
        await session.flush()

        # Dispel illusion
        rev_res = await core_illusions.reveal_illusory_wall(session, char, wall_cell)
        assert rev_res["ok"]
        assert wall_cell.is_passable
        assert wall_cell.has_chest
        assert wall_cell.name == "Тайный грот"


@pytest.mark.asyncio
async def test_hall_of_legends_server_firsts():
    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="legend_hero")
        session.add(user)
        await session.flush()

        char = Character(user_id=user.id, name="FirstSlayer", character_class="warrior", level=12, stats_locked=True)
        session.add(char)
        await session.flush()

        key = f"first_boss_kill_{_rand_tg()}"
        ok1 = await core_legends.record_server_first(session, key, "Первое убийство Левиафана", char)
        assert ok1

        # Second attempt for same key returns False (already achieved)
        ok2 = await core_legends.record_server_first(session, key, "Первое убийство Левиафана", char)
        assert not ok2

        records = await core_legends.get_hall_of_legends(session)
        assert len(records) >= 1
        txt = core_legends.hall_of_legends_text(records)
        assert "FirstSlayer" in txt


def test_reactive_dialogue():
    char_good = Character(name="SaintHero", karma_score=300)
    char_evil = Character(name="DarkSinner", karma_score=-300)

    # Siege context
    dlg_siege = core_dialogue.generate_reactive_dialogue(char_good, "Капитан Стражи", "guard", {"has_siege": True})
    assert "осадные орудия" in dlg_siege

    # Evil karma context
    dlg_evil = core_dialogue.generate_reactive_dialogue(char_evil, "Старейшина", "storyteller", {})
    assert "осквернитель" in dlg_evil

    # Good karma context
    dlg_good = core_dialogue.generate_reactive_dialogue(char_good, "Старейшина", "storyteller", {})
    assert "благословение" in dlg_good
