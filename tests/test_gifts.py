"""Прямой обмен «рука в руку» (IDEAS-next, пункт 2).

Запуск: python3 -m pytest -q tests/test_gifts.py

Зачем. Экономика умела продавать только через аукцион: витрина, комиссия,
24 часа. Игроки, стоящие на одной клетке, не могли передать ни вещь, ни
монеты. Здесь проверяется домен (`core/gifts.py`) и подключение экранов
к боту; обман возможен только в сторону «отдать своё», поэтому главные
риски — потеря вещи при гонке и подарка чужой сумки. Их и закрепляем.
"""
import os
import sys

import pytest
from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _seed import pin, unique_id, unique_name  # noqa: E402

pin(931)

from core.database import async_session
from core.models import (
    Cell, Character, InventoryItem, Item, ItemInstance, Location, User,
)
from core.enums import ItemType


async def _mk_pair(session, cell=None):
    """Два героя на одной клетке; в возвращаемом словере — и telegram id."""
    loc = Location(name=unique_name("Поляна"), description="тест", grid_size=10)
    session.add(loc)
    await session.flush()
    if cell is None:
        cell = Cell(location_id=loc.id, x=1, y=1, name="Место",
                    tile_type="road", is_passable=True)
        session.add(cell)
        await session.flush()

    heroes = {}
    for tag in ("giver", "getter"):
        user = User(telegram_id=unique_id(), username=unique_name(tag))
        session.add(user)
        await session.flush()
        ch = Character(user_id=user.id, name=unique_name("G"),
                       character_class="warrior", level=10, stats_locked=True,
                       location_id=loc.id, cell_id=cell.id, floor=0,
                       bronze=2000)
        session.add(ch)
        await session.flush()
        heroes[tag] = (user, ch)
    return heroes, loc, cell


async def _mk_item(session, owner, *, quantity=1, instance=True,
                   is_sellable=True, equipped=False, in_stash=False):
    item = Item(name=unique_name("Клинок"), description="тест",
                item_type=ItemType.WEAPON, price=50,
                is_sellable=is_sellable)
    session.add(item)
    await session.flush()
    inst = None
    if instance:
        inst = ItemInstance(uid=f"GF{unique_id()}", item_id=item.id,
                            owner_character_id=owner.id)
        session.add(inst)
        await session.flush()
    inv = InventoryItem(character_id=owner.id, item_id=item.id,
                        instance_id=inst.id if inst else None,
                        quantity=quantity, is_equipped=equipped,
                        in_stash=in_stash)
    session.add(inv)
    await session.flush()
    return item, inst, inv


@pytest.mark.asyncio
async def test_gift_instance_moves_ownership_and_history():
    from core import gifts

    async with async_session() as session:
        heroes, _, _ = await _mk_pair(session)
        giver, getter = heroes["giver"][1], heroes["getter"][1]
        item, inst, inv = await _mk_item(session, giver)

        res = await gifts.gift_item(session, giver, getter, inv, 1)
        assert res["ok"], res
        await session.commit()

    async with async_session() as session:
        mine = (await session.execute(
            select(InventoryItem).where(InventoryItem.character_id == giver.id)
        )).scalars().all()
        theirs = (await session.execute(
            select(InventoryItem).where(InventoryItem.character_id == getter.id)
            .where(InventoryItem.instance_id == inst.id)
        )).scalars().all()
        assert mine == [], "у дарителя вещь обязана исчезнуть"
        assert len(theirs) == 1, "у получателя — ровно одна копия"
        inst_fresh = await session.get(ItemInstance, inst.id)
        assert inst_fresh.owner_character_id == getter.id
        assert inst_fresh.trade_count == 1
        from core.models import ItemHistory
        row = (await session.execute(
            select(ItemHistory).where(ItemHistory.instance_id == inst.id)
            .where(ItemHistory.event == "gifted")
        )).scalars().first()
        assert row is not None and getter.name in (row.detail or "")
        item_fresh = await session.get(Item, item.id)
        assert item_fresh.is_sellable  # подарок не «съедает» флаги шаблона


@pytest.mark.asyncio
async def test_gift_stack_splits_and_merges():
    from core import gifts

    async with async_session() as session:
        heroes, _, _ = await _mk_pair(session)
        giver, getter = heroes["giver"][1], heroes["getter"][1]
        item, _, inv = await _mk_item(session, giver, quantity=10,
                                      instance=False)
        # У получателя уже есть этот предмет — дарение подсыпает в
        # существующую строку, а не плодит дубли.
        getter_row = InventoryItem(character_id=getter.id, item_id=item.id,
                                   quantity=2)
        session.add(getter_row)
        await session.flush()

        res = await gifts.gift_item(session, giver, getter, inv, 3)
        assert res["ok"] and res["qty"] == 3
        await session.flush()
        assert getter_row.quantity == 5, "влилось в существующую строку"
        assert inv.quantity == 7, "у дарителя убавилось"

        res2 = await gifts.gift_item(session, giver, getter, inv, 7)
        assert res2["ok"] and res2["qty"] == 7
        await session.commit()

    async with async_session() as session:
        mine = (await session.execute(
            select(InventoryItem).where(InventoryItem.character_id == giver.id)
        )).scalars().all()
        assert mine == [], "стак выдан весь"
        theirs = (await session.execute(
            select(InventoryItem).where(InventoryItem.character_id == getter.id)
            .where(InventoryItem.item_id == item.id)
        )).scalars().all()
        assert len(theirs) == 1, "одна строка, а не россыпь дублей"
        assert theirs[0].quantity == 12


@pytest.mark.asyncio
async def test_gift_refuses_equipped_stash_unsellable_far():
    from core import gifts

    async with async_session() as session:
        heroes, loc, cell = await _mk_pair(session)
        giver, getter = heroes["giver"][1], heroes["getter"][1]
        _, _, inv_eq = await _mk_item(session, giver, equipped=True)
        _, _, inv_stash = await _mk_item(session, giver, in_stash=True)
        _, _, inv_locked = await _mk_item(session, giver, is_sellable=False)
        res = await gifts.gift_item(session, giver, getter, inv_eq, 1)
        assert not res["ok"] and "сними" in res["reason"]
        res = await gifts.gift_item(session, giver, getter, inv_stash, 1)
        assert not res["ok"] and "карман" in res["reason"]
        res = await gifts.gift_item(session, giver, getter, inv_locked, 1)
        assert not res["ok"] and "нельзя передать" in res["reason"]

        # Даритель ушёл на другую клетку — обмен невозможен.
        away = Cell(location_id=loc.id, x=5, y=5, name="Дальше",
                    tile_type="road", is_passable=True)
        session.add(away)
        await session.flush()
        giver.cell_id = away.id
        _, _, inv_free = await _mk_item(session, giver)
        res = await gifts.gift_item(session, giver, getter, inv_free, 1)
        assert not res["ok"] and "не рядом" in res["reason"]
        giver.cell_id = cell.id
        # Больше самого себя никому:
        res = await gifts.gift_item(session, giver, giver, inv_free, 1)
        assert not res["ok"]
        await session.rollback()


@pytest.mark.asyncio
async def test_gift_gold_moves_purse():
    from core import gifts
    from engine.currency import total_in_bronze

    async with async_session() as session:
        heroes, _, _ = await _mk_pair(session)
        giver, getter = heroes["giver"][1], heroes["getter"][1]
        giver.bronze = 700
        getter.bronze = 0
        await session.flush()

        res = await gifts.gift_gold(session, giver, getter, 300)
        assert res["ok"]
        assert total_in_bronze(giver) == 400
        assert total_in_bronze(getter) == 300

        res = await gifts.gift_gold(session, giver, getter, 10_000)
        assert not res["ok"] and "Не хватает" in res["reason"]
        assert total_in_bronze(giver) == 400, "отказ не должен списывать"
        res = await gifts.gift_gold(session, giver, getter, 0)
        assert not res["ok"]
        await session.rollback()


@pytest.mark.asyncio
async def test_unreachable_recipient_cannot_receive():
    """Ссылка-колбэк с чужим id получателя ничего не переводит."""
    from core import gifts

    async with async_session() as session:
        heroes, _, _ = await _mk_pair(session)
        giver = heroes["giver"][1]
        strangers, _, _ = await _mk_pair(session)  # чужая пара
        stranger = strangers["getter"][1]
        _, _, inv = await _mk_item(session, giver)
        res = await gifts.gift_item(session, giver, stranger, inv, 1)
        assert not res["ok"] and "не рядом" in res["reason"]
        await session.rollback()


def test_bot_entrypoints():
    pytest.importorskip("aiogram")
    from bot.keyboards.inline import inspect_keyboard
    kb = inspect_keyboard(has_mob=False, has_npc=False, has_chest=False,
                          has_players=True)
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "gift_select" in datas

    from bot.handlers.gifts import router
    from bot.handlers import routers
    assert router in routers, "роутер подарков не подключён к диспетчеру"

    class _Probe:
        def __init__(self, data):
            self.data = data

    wanted = {"gift_select", "gift_to:1", "gift_pick:1:1",
              "gift_confirm:1:item:1:1", "gift_gold:1:100"}
    for cb in wanted:
        probe = _Probe(cb)
        hit = any(
            any((f.callback(probe) if hasattr(f, "callback") else False)
                for f in (h.filters or []))
            for h in router.callback_query.handlers)
        assert hit, f"нет обработчика на {cb}"
