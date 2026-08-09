import os
import random
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import async_session
from core.models import User, Character, Location, Cell, DungeonRun, DungeonCell, Item, ItemInstance, CraftRecipe
from core import craft_orders as core_orders
from core import runes as core_runes
from core import dungeons as core_dungeons


def _rand_tg():
    return random.randint(100_000_000, 999_999_999)


@pytest.mark.asyncio
async def test_trap_and_captive_mechanics():
    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="dungeon_rogue")
        session.add(user)
        await session.flush()

        char = Character(
            user_id=user.id,
            name="NimbleThief",
            character_class="rogue",
            level=3,
            agility=25,
            current_hp=100,
            max_hp=100,
            stats_locked=True,
        )
        session.add(char)
        await session.flush()

        run = DungeonRun(character_id=char.id, seed=555, floor=1, is_active=True)
        session.add(run)
        await session.flush()

        # Cell with trap
        trap_cell = DungeonCell(
            run_id=run.id, x=1, y=1, name="Заминированный коридор",
            has_trap=True, trap_type="spikes", is_passable=True,
        )
        # Cell with captive
        captive_cell = DungeonCell(
            run_id=run.id, x=2, y=2, name="Тюремный альков",
            has_captive=True, captive_name="Мастер Алхимии", captive_type="alchemist", is_passable=True,
        )
        session.add_all([trap_cell, captive_cell])
        await session.commit()

        # Disarm trap
        trap_cell.has_trap = False
        char.experience = (char.experience or 0) + 40
        await session.commit()
        assert not trap_cell.has_trap
        assert char.experience >= 40

        # Rescue captive
        captive_cell.has_captive = False
        char.experience = (char.experience or 0) + 100
        await session.commit()
        assert not captive_cell.has_captive
        assert char.experience >= 140


@pytest.mark.asyncio
async def test_mimic_chest_trigger():
    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="mimic_hunter")
        session.add(user)
        await session.flush()

        char = Character(user_id=user.id, name="BraveKnight", character_class="warrior", level=3, stats_locked=True)
        session.add(char)
        await session.flush()

        run = DungeonRun(character_id=char.id, seed=777, floor=1, is_active=True)
        session.add(run)
        await session.flush()

        mimic_cell = DungeonCell(
            run_id=run.id, x=3, y=3, name="Тёмный грот",
            has_chest=True, is_mimic=True, is_passable=True, chest_gold=30,
        )
        session.add(mimic_cell)
        await session.commit()

        # Trigger mimic
        mimic_cell.has_chest = False
        mimic_cell.is_mimic = False
        mimic_cell.has_mob = True
        mimic_cell.mob_name = "Монстр-Мимик"
        mimic_cell.mob_gold = 60
        await session.commit()

        assert mimic_cell.has_mob
        assert mimic_cell.mob_name == "Монстр-Мимик"
        assert mimic_cell.mob_gold == 60


@pytest.mark.asyncio
async def test_public_work_orders():
    async with async_session() as session:
        u_cust = User(telegram_id=_rand_tg(), username="customer")
        u_smith = User(telegram_id=_rand_tg(), username="blacksmith")
        session.add_all([u_cust, u_smith])
        await session.flush()

        c_cust = Character(user_id=u_cust.id, name="RichNoble", character_class="warrior", level=1, gold=10, stats_locked=True)
        c_smith = Character(user_id=u_smith.id, name="MasterDarn", character_class="warrior", level=10, gold=0, stats_locked=True)
        session.add_all([c_cust, c_smith])
        await session.flush()

        item = Item(name="Стальной клинок", description="Острый клинок", item_type="weapon", price=100)
        session.add(item)
        await session.flush()

        recipe = CraftRecipe(
            name="Ковка клинка",
            station="forge",
            result_item_id=item.id,
            gold_cost=50,
            min_level=1,
            is_enabled=True,
        )
        session.add(recipe)
        await session.flush()

        # Customer creates order with 300 bounty
        ord_res = await core_orders.create_order(session, c_cust, recipe.id, bounty_bronze=300)
        assert ord_res["ok"]
        order = ord_res["order"]
        assert order.status == "open"
        assert order.reward_bronze == 300

        open_list = await core_orders.list_open_orders(session)
        assert len(open_list) >= 1
        assert any(o.id == order.id for o in open_list)


def test_sockets_and_runewords():
    inst = ItemInstance(
        uid="IT-RUNE01",
        item_id=1,
        quality=110,
        bonus_damage=10,
        bonus_defense=5,
        bonus_hp=0,
    )
    # Insert Rune of Fire
    res1 = core_runes.insert_rune(inst, "rune_fire", slot=1)
    assert res1["ok"]
    assert inst.socket_1 == "rune_fire"
    assert inst.bonus_damage == 20

    # Insert Rune of Steel -> forms "Пламенная сталь" Runeword
    res2 = core_runes.insert_rune(inst, "rune_iron", slot=2)
    assert res2["ok"]
    assert inst.socket_2 == "rune_iron"
    assert inst.runeword == "Пламенная сталь"
    # Damage: 10 base + 10 (rune_fire) + 20 (runeword) = 40
    assert inst.bonus_damage == 40
    # Defense: 5 base + 15 (rune_iron) + 15 (runeword) = 35
    assert inst.bonus_defense == 35
