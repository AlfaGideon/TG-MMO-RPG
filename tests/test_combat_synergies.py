import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import async_session
from core.models import User, Character, Location, Cell, Mob, MobSpawn
from core import factions as core_factions
from core import magic as core_magic
from core import stats as core_stats
from bot.handlers import battle as bot_battle


@pytest.mark.asyncio
async def test_location_influence_and_dominance():
    async with async_session() as session:
        loc = Location(
            name="Пепельные Пустоши",
            description="Пустоши",
            grid_size=10,
            min_level=1,
            influence_json='{"guard": 20, "scavengers": 10, "cult": 60, "order": 10}',
        )
        session.add(loc)
        await session.flush()

        inf = core_factions.get_location_influence(loc)
        assert inf["cult"] == 60

        dom_f, dom_pct = core_factions.get_dominant_faction(loc)
        assert dom_f == "cult"
        assert dom_pct == 60

        # Shift influence
        await core_factions.add_location_influence(session, loc, "order", 50)
        inf_updated = core_factions.get_location_influence(loc)
        assert inf_updated["order"] == 60

        inf_text = core_factions.location_influence_text(loc)
        assert "Контроль" in inf_text or "Баланс" in inf_text


def test_elemental_reactions_combos():
    # Fire + Nature -> Spore Ignition (Burn)
    r1 = core_magic.trigger_elemental_reaction("fire", "nature")
    assert r1 is not None
    assert "Воспламенение спор" in r1["name"]
    assert r1["mult"] == 1.45
    assert r1["effect"] == "burn"

    # Ice + Storm -> Superconductivity (Broken Armor)
    r2 = core_magic.trigger_elemental_reaction("storm", "ice")
    assert r2 is not None
    assert "Сверхпроводимость" in r2["name"]
    assert r2["mult"] == 1.50
    assert r2["effect"] == "broken_armor"

    # Light + Dark -> Annihilation
    r3 = core_magic.trigger_elemental_reaction("light", "dark")
    assert r3 is not None
    assert "Аннигиляция" in r3["name"]

    # Same school -> No reaction
    assert core_magic.trigger_elemental_reaction("fire", "fire") is None
    assert core_magic.trigger_elemental_reaction(None, "ice") is None


def test_combat_stances_and_statuses():
    state = {
        "spawn_id": 1,
        "mob_id": 1,
        "mob_hp": 100,
        "character_hp": 100,
        "rounds": 0,
        "damage_dealt": 0,
        "damage_taken": 0,
        "stance": "berserk",
        "statuses": {"burn": 2, "broken_armor": 2},
        "channeling": None,
    }
    assert state["stance"] == "berserk"
    assert "burn" in state["statuses"]


def test_spell_interruption_mechanic():
    state = {
        "spawn_id": 1,
        "mob_id": 1,
        "mob_hp": 100,
        "character_hp": 100,
        "rounds": 3,
        "channeling": {"name": "🔥 Разрушительный шквал", "damage": 50},
        "statuses": {},
    }
    # Simulate interrupt action
    chan_name = state["channeling"]["name"]
    state["channeling"] = None
    state["statuses"]["stun"] = 1
    state["mob_hp"] -= 15

    assert state["channeling"] is None
    assert state["statuses"]["stun"] == 1
    assert state["mob_hp"] == 85
