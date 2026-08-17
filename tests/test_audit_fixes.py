"""Баги из AUDIT-BUGS.md: сироты аукциона, секрет, колбэки, квесты.

Запуск: python3 -m pytest -q tests/test_audit_fixes.py

Закрывает пункты № 81–84 и № 87 из `IDEAS-100.md`:
  * 81 — `_return_to_owner` создавал `InventoryItem` на удалённого
    продавца (сирота, которую никто не увидит);
  * 82 — лот скупщика через 72 ч исчезал из мира вопреки документации;
  * 83 — `ADMIN_SECRET_KEY` имел публичный дефолт «shadow-lands-secret»:
    подделать cookie мог кто угодно;
  * 84 — колбэк открытия вещи ссылался на позицию в списке: из старого
    сообщения открывался соседний предмет;
  * 87 — модель `Quest` и задания в сиде были, а выдачи и сдачи в боте нет.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Детерминизм (пункт № 5): игровой random спинован своей константой,
# а уникальные telegram_id берутся вне seed — см. tests/_seed.py.
from _seed import pin, unique_id  # noqa: E402

pin(102)

from core.database import async_session
from core.enums import AuctionStatus, QuestStatus
from core.models import (AuctionLot, Character, CharacterQuest, InventoryItem,
                         Item, ItemInstance, Quest, User)


def _rand_tg():
    return unique_id()


async def _make_hero(session, name="Hero", level=5):
    user = User(telegram_id=_rand_tg(), username=name.lower())
    session.add(user)
    await session.flush()
    char = Character(user_id=user.id, name=name, character_class="warrior",
                     level=level, stats_locked=True)
    session.add(char)
    await session.flush()
    return char


async def _make_instance(session, price=200, name="Клинок судьбы"):
    from core.loot import new_uid

    item = Item(name=name, description="—", item_type="weapon",
                rarity="rare", price=price)
    session.add(item)
    await session.flush()
    inst = ItemInstance(uid=new_uid(), item_id=item.id, quality=100)
    session.add(inst)
    await session.flush()
    return item, inst


# ── № 81: вещь удалённого продавца не становится сиротой ──

@pytest.mark.asyncio
async def test_lot_of_deleted_seller_goes_to_npc_not_orphan():
    from sqlalchemy import select

    from core import auction as core_auction

    async with async_session() as session:
        item, inst = await _make_instance(session)
        ghost_id = 999_999_999          # продавца с таким id не существует
        lot = AuctionLot(seller_id=ghost_id, item_id=item.id,
                         instance_id=inst.id, price=300,
                         status=AuctionStatus.ACTIVE.value)
        session.add(lot)
        await session.flush()

        # character=None + отсутствующий продавец: раньше здесь появлялась
        # строка инвентаря на мертвеца.
        await core_auction._return_to_owner(session, lot, None, event="expired")
        await session.flush()

        orphans = (await session.execute(
            select(InventoryItem)
            .where(InventoryItem.character_id == ghost_id)
        )).scalars().all()
        assert not orphans, "создана сирота на несуществующего персонажа"

        npc_lots = (await session.execute(
            select(AuctionLot)
            .where(AuctionLot.instance_id == inst.id)
            .where(AuctionLot.is_npc_lot == True)  # noqa: E712
        )).scalars().all()
        assert npc_lots, "вещь исчезла из мира вместо витрины скупщика"
        assert npc_lots[0].price > 0
        await session.rollback()


@pytest.mark.asyncio
async def test_lot_returns_to_living_seller_as_before():
    """Обычный случай не сломан: живой продавец получает вещь в сумку."""
    from sqlalchemy import select

    from core import auction as core_auction

    async with async_session() as session:
        seller = await _make_hero(session, "Seller")
        item, inst = await _make_instance(session)
        lot = AuctionLot(seller_id=seller.id, item_id=item.id,
                         instance_id=inst.id, price=250,
                         status=AuctionStatus.ACTIVE.value)
        session.add(lot)
        await session.flush()

        await core_auction._return_to_owner(session, lot, seller, event="expired")
        await session.flush()

        back = (await session.execute(
            select(InventoryItem)
            .where(InventoryItem.character_id == seller.id)
            .where(InventoryItem.instance_id == inst.id)
        )).scalars().all()
        assert len(back) == 1, "вещь не вернулась продавцу"
        assert inst.owner_character_id == seller.id
        await session.rollback()


# ── № 82: лот скупщика не исчезает из мира ──

@pytest.mark.asyncio
async def test_expired_npc_lot_is_relisted_not_destroyed():
    from datetime import timedelta

    from sqlalchemy import select

    from core import auction as core_auction
    from core import dates

    async with async_session() as session:
        item, inst = await _make_instance(session, name="Забытый шлем")
        lot = AuctionLot(seller_id=None, item_id=item.id, instance_id=inst.id,
                         price=400, status=AuctionStatus.ACTIVE.value,
                         is_npc_lot=True,
                         expires_at=dates.utcnow() - timedelta(hours=1))
        session.add(lot)
        await session.flush()

        await core_auction.sweep_expired(session)
        await session.flush()

        alive = (await session.execute(
            select(AuctionLot)
            .where(AuctionLot.instance_id == inst.id)
            .where(AuctionLot.status == AuctionStatus.ACTIVE.value)
        )).scalars().all()
        assert alive, "вещь скупщика исчезла из мира после истечения срока"
        assert alive[0].expires_at is None, "перевыставленный лот должен быть бессрочным"
        await session.rollback()


# ── № 83: ключ подписи сессий ──

def test_admin_secret_is_not_public_default():
    from admin import auth

    assert auth.SECRET, "ключ пустой"
    assert auth.SECRET not in auth._WEAK_KEYS, \
        "используется опубликованный в репозитории ключ"
    assert len(auth.SECRET) >= 32, "слишком короткий ключ подписи"


def test_admin_secret_prefers_env_but_rejects_examples(monkeypatch, tmp_path):
    from admin import auth

    monkeypatch.setenv("ADMIN_SECRET_KEY", "настоящий-ключ-из-окружения")
    assert auth._load_secret() == "настоящий-ключ-из-окружения"

    # Пример из .env.example не должен приниматься за настоящий ключ.
    monkeypatch.setenv("ADMIN_SECRET_KEY", "super-secret-key-change-me")
    assert auth._load_secret() != "super-secret-key-change-me"


def test_admin_secret_file_is_git_ignored():
    """Сгенерированный ключ не должен попасть в репозиторий."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ignore = open(os.path.join(root, ".gitignore"), encoding="utf-8").read()
    assert "data/" in ignore, "каталог data/ обязан игнорироваться git"


# ── № 84: колбэк ссылается на вещь, а не на позицию ──

def test_inventory_callback_carries_item_id():
    from types import SimpleNamespace

    from bot.keyboards.inline import inventory_section_keyboard

    def fake(inv_id, name):
        return SimpleNamespace(
            id=inv_id, is_equipped=False, quantity=1, instance_id=None,
            instance=None, item=SimpleNamespace(icon="🗡"),
            display_name=lambda: name)

    items = [fake(11, "Меч"), fake(22, "Щит")]
    kb = inventory_section_keyboard(items, "gear", page=0)
    data = [b.callback_data for row in kb.inline_keyboard for b in row]

    assert "inv_book:gear:0:11" in data, "в колбэке нет id вещи"
    assert "inv_book:gear:1:22" in data


@pytest.mark.asyncio
async def test_stale_callback_does_not_open_neighbour_item():
    """Если вещь продали, старая кнопка честно сообщает об этом."""
    from core.models import Item as ItemModel

    async with async_session() as session:
        char = await _make_hero(session, "Stale")
        sword = ItemModel(name="Меч А", description="—", item_type="weapon",
                          rarity="common", price=10)
        shield = ItemModel(name="Щит Б", description="—", item_type="armor",
                           rarity="common", price=10)
        session.add_all([sword, shield])
        await session.flush()
        inv_a = InventoryItem(character_id=char.id, item_id=sword.id, quantity=1)
        inv_b = InventoryItem(character_id=char.id, item_id=shield.id, quantity=1)
        session.add_all([inv_a, inv_b])
        await session.flush()
        gone_id, alive_id = inv_a.id, inv_b.id

        # Первую вещь «продали» из другого сообщения.
        await session.delete(inv_a)
        await session.flush()

        bucket = [inv_b]
        found = next((i for i, inv in enumerate(bucket) if inv.id == gone_id), None)
        assert found is None, "исчезнувшая вещь не должна находиться"
        # А по живому id — находится и это именно она.
        found_alive = next(i for i, inv in enumerate(bucket) if inv.id == alive_id)
        assert bucket[found_alive].item_id == shield.id
        await session.rollback()


# ── № 87: задания выдаются и сдаются ──

@pytest.mark.asyncio
async def test_kill_quest_full_cycle():
    from core import quests as core_quests
    from engine.currency import total_in_bronze

    async with async_session() as session:
        char = await _make_hero(session, "Quester", level=3)
        quest = Quest(name="Тестовая охота", description="Убей 2 крыс.",
                      objective_type="kill", objective_target="Тест-крыса",
                      objective_count=2, reward_gold=75, reward_exp=40,
                      min_level=1)
        session.add(quest)
        await session.flush()

        offered = await core_quests.available_for(session, char)
        assert any(q.id == quest.id for q in offered), "задание не предложено"

        assert (await core_quests.accept(session, char, quest.id))["ok"] is True
        # Дважды одно задание не берётся.
        assert (await core_quests.accept(session, char, quest.id))["ok"] is False
        assert not any(q.id == quest.id
                       for q in await core_quests.available_for(session, char))

        active = await core_quests.active_for(session, char)
        cq = next(c for c in active if c.quest_id == quest.id)

        # Сдать недовыполненное нельзя.
        assert (await core_quests.turn_in(session, char, cq.id))["ok"] is False

        # Чужая тварь прогресс не двигает.
        await core_quests.record_kill(session, char, "Другой моб")
        assert await core_quests.progress_of(session, char, cq) == 0

        await core_quests.record_kill(session, char, "Тест-крыса")
        assert await core_quests.progress_of(session, char, cq) == 1
        lines = await core_quests.record_kill(session, char, "тест-крыса")  # регистр
        assert await core_quests.progress_of(session, char, cq) == 2
        assert any("можно сдавать" in l for l in lines)

        money_before = total_in_bronze(char)
        exp_before = char.experience or 0
        res = await core_quests.turn_in(session, char, cq.id)
        assert res["ok"] is True
        assert total_in_bronze(char) == money_before + 75
        assert (char.experience or 0) == exp_before + 40
        assert cq.status == QuestStatus.COMPLETED

        # Повторно сдать нельзя.
        assert (await core_quests.turn_in(session, char, cq.id))["ok"] is False
        await session.rollback()


@pytest.mark.asyncio
async def test_collect_quest_consumes_items():
    """Сбор считается по сумке, а предметы уходят заказчику при сдаче."""
    from sqlalchemy import select

    from core import quests as core_quests

    async with async_session() as session:
        char = await _make_hero(session, "Gatherer", level=2)
        herb = Item(name="Тест-трава", description="—", item_type="material",
                    rarity="common", price=5)
        session.add(herb)
        await session.flush()
        quest = Quest(name="Тестовый сбор", description="Принеси 3 травы.",
                      objective_type="collect", objective_target="Тест-трава",
                      objective_count=3, reward_gold=30, reward_exp=10,
                      min_level=1)
        session.add(quest)
        await session.flush()

        await core_quests.accept(session, char, quest.id)
        cq = next(c for c in await core_quests.active_for(session, char)
                  if c.quest_id == quest.id)
        assert await core_quests.progress_of(session, char, cq) == 0
        assert (await core_quests.turn_in(session, char, cq.id))["ok"] is False

        session.add(InventoryItem(character_id=char.id, item_id=herb.id,
                                  quantity=5))
        await session.flush()
        assert await core_quests.progress_of(session, char, cq) == 5

        res = await core_quests.turn_in(session, char, cq.id)
        assert res["ok"] is True

        left = await session.scalar(
            select(InventoryItem.quantity)
            .where(InventoryItem.character_id == char.id)
            .where(InventoryItem.item_id == herb.id)
        )
        assert left == 2, f"должно остаться 5-3=2, осталось {left}"
        await session.rollback()


def test_quest_handlers_registered():
    """Кнопка и обработчики заданий существуют — иначе входа снова нет."""
    from bot.handlers import routers
    from bot.handlers.quests import router as quests_router
    from bot.keyboards.inline import main_menu_keyboard

    assert quests_router in routers

    data = [b.callback_data for row in
            main_menu_keyboard(has_character=True).inline_keyboard for b in row]
    assert "quests_menu" in data

    class _CB:
        def __init__(self, d):
            self.data = d

    def has(cb):
        for handler in quests_router.callback_query.handlers:
            for flt in handler.filters or []:
                try:
                    if flt.callback(_CB(cb)):
                        return True
                except Exception:
                    continue
        return False

    assert has("quests_menu") and has("quest_take:1") and has("quest_turnin:1")
    assert not has("выдуманная_кнопка")
