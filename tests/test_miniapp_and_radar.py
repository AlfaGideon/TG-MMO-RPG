import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import async_session
from core.models import User, Character, Location, Item, ItemInstance, InventoryItem
from core import stats as core_stats
from core import realtime as core_realtime
from core import ambient as core_ambient


def test_ambient_sound_profiles():
    safe_amb = core_ambient.get_ambient_profile("safe")
    assert safe_amb["soundscape"] == "campfire_crackles"
    assert safe_amb["reverb"] < 0.5

    dungeon_amb = core_ambient.get_ambient_profile("dungeon")
    assert dungeon_amb["soundscape"] == "water_drips_echo"
    assert dungeon_amb["reverb"] >= 0.8


def test_gear_loadout_simulator():
    char = Character(name="SimHero", strength=20, agility=15, endurance=15, max_hp=120)

    # Simulated weapon and armor
    mock_weapon = InventoryItem(item=Item(name="Меч дракона", item_type="weapon", price=500), instance_id=1)
    mock_weapon.instance = ItemInstance(uid="IT-SIM01", item_id=1, bonus_damage=35, bonus_strength=5)

    mock_armor = InventoryItem(item=Item(name="Кираса света", item_type="armor", price=400), instance_id=2)
    mock_armor.instance = ItemInstance(uid="IT-SIM02", item_id=2, bonus_defense=25, bonus_hp=40)

    sim = core_stats.simulate_gear_loadout(char, [mock_weapon, mock_armor])
    assert sim["attack_power"] == 25 + 35  # (20 + 5) + 35 = 60
    assert sim["stats"]["max_hp"] == 120 + 40  # 160
    assert sim["damage_reduction"] >= 25


@pytest.mark.asyncio
async def test_realtime_radar_hud():
    core_realtime.clear()

    # Publish events
    await core_realtime.publish("battle_victory", {
        "character_name": "Ragnar",
        "mob_name": "Пещерный паук",
        "gold": 45,
        "exp": 60,
    })
    await core_realtime.publish("chest_opened", {
        "name": "Loki",
    })
    await core_realtime.publish("outpost_captured", {
        "outpost_name": "Северный Форт",
        "faction": "Стража",
    })

    feed = core_realtime.get_radar_feed(limit=5)
    assert len(feed) == 3
    assert any("Ragnar" in line for line in feed)
    assert any("Северный Форт" in line for line in feed)
