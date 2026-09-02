"""Летопись сервера для игроков (IDEAS-100 № 60) и напоминания (IDEAS-next № 10).

Запуск: python3 -m pytest -q tests/test_legends_and_reminders.py

Зачем. Запись `ServerRecord` и тексты Зала Славы были написаны, но жили
только в тестах: бот не показывал летопись, а подвиги не записывались в
бою. Напоминаний об истечении лотов, закрытии портала и зависших вызовах
на дуэль не было вовсе — игрок узнавал о финише событий, только заглянув
в бота сам.

Проверяется связка:
* убийство мирового босса -> запись «первый разгром» (ровно одна, навсегда);
* завершение катаклизма -> веха «первое пережитое бедствие» без автора;
* экран летописи экранирует имена (HTML-инъекция именем героя);
* в боте есть кнопка и зарегистрированный обработчик «🏛 Летопись»;
* collect_due_reminders находит истекающий лот (продавцу и лидеру торгов),
  гасит повторы, молчит заранее, напоминает о закрывающемся портале и о
  висящем вызове дуэли.
"""
import os
import sys
import time

import pytest
from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _seed import pin, unique_id, unique_name  # noqa: E402

pin(927)

from core.database import async_session
from core.models import (
    AuctionLot, Character, DungeonTemplate, Item, ItemInstance, ServerRecord,
    User, WorldEvent,
)
from core.enums import AuctionStatus, ItemType


async def _mk_hero(session, name=None, level=10):
    user = User(telegram_id=unique_id(), username=name or None)
    session.add(user)
    await session.flush()
    char = Character(user_id=user.id, name=name or unique_name("Hero"),
                     character_class="warrior", level=level, stats_locked=True)
    session.add(char)
    await session.flush()
    return user, char


async def _silence_world(session):
    """Снять события, оставленные прежними прогонами: summon_boss и strike
    отказываются плодить активных боссов/бедствия."""
    for ev in (await session.execute(
            select(WorldEvent).where(WorldEvent.is_active == True)  # noqa: E712
    )).scalars().all():
        ev.is_active = False
    await session.flush()


# ── летопись: запись подвигов ────────────────────────────────

@pytest.mark.asyncio
async def test_boss_first_kill_becomes_record_once():
    from core import worldevents as we
    from core import legends as lg

    boss_key = next(iter(we.BOSSES))
    async with async_session() as session:
        await _silence_world(session)
        # Чистый лист для СВОЕГО ключа — иначе рекорд прежнего прогона
        # сделал бы проверку владельца плавающей.
        for old in (await session.execute(
                select(ServerRecord)
                .where(ServerRecord.record_key == f"boss:{boss_key}")
        )).scalars().all():
            await session.delete(old)
        await session.commit()

    async with async_session() as session:
        _, slayer = await _mk_hero(session)
        _, latecomer = await _mk_hero(session)
        slayer_name = slayer.name

        ev = await we.summon_boss(session, boss_key, hours=0.05)
        hp_left, _ = await we.hit_boss(session, slayer, int(ev.max_hp) + 10)
        assert hp_left == 0
        await session.commit()

    async with async_session() as session:
        rows = (await session.execute(
            select(ServerRecord).where(ServerRecord.record_key == f"boss:{boss_key}")
        )).scalars().all()
        assert len(rows) == 1, "запись «первый разгром» должна быть ровно одна"

        # Второй раз того же босса — «первый» не перетирается.
        await _silence_world(session)
        ev2 = await we.summon_boss(session, boss_key, hours=0.05)
        await we.hit_boss(session, latecomer, int(ev2.max_hp) + 10)
        await session.commit()

    async with async_session() as session:
        rows = (await session.execute(
            select(ServerRecord).where(ServerRecord.record_key == f"boss:{boss_key}")
        )).scalars().all()
        assert len(rows) == 1
        assert rows[0].holder_character_name == slayer_name, (
            "рекорд должен принадлежать добившему и не перетираться "
            "поздними убийцами")
        txt = lg.hall_of_legends_text(rows)
        assert "Зал Славы" in txt


@pytest.mark.asyncio
async def test_survived_cataclysm_recorded_without_holder():
    from core import worldevents as we
    from core.models import ServerRecord
    from sqlalchemy import select

    kind = next(iter(we.KINDS))
    async with async_session() as session:
        await _silence_world(session)
        for old in (await session.execute(
                select(ServerRecord)
                .where(ServerRecord.record_key == f"cataclysm:{kind}")
        )).scalars().all():
            await session.delete(old)
        await session.commit()

    async with async_session() as session:
        ev = await we.strike(session, kind, hours=0.05)
        await session.commit()
        await we.end_cataclysm(session, ev.id)
        await session.commit()

    async with async_session() as session:
        row = (await session.execute(
            select(ServerRecord).where(ServerRecord.record_key == f"cataclysm:{kind}")
        )).scalars().first()
        assert row is not None, "завершение бедствия должно оставить веху"
        assert row.holder_character_name == "Сервер"
        assert row.holder_character_id is None


# ── летопись: экраны и кнопки ────────────────────────────────

def test_hall_text_escapes_names():
    """Имя героя — ввод игрока; экран отдается с parse_mode=HTML."""
    from engine import legends

    html = legends.hall_text([{
        "key": "k", "title": "Первый <b>подвиг</b>", "holder": 'Hacks<b>x</b>',
        "ts": int(time.time()),
    }])
    assert "<b>подвиг</b>" not in html          # не размонтируется в разметку
    assert "Hacks&lt;b&gt;" in html             # экранирован
    assert "<b>Первый &lt;b&gt;подвиг&lt;/b&gt;</b>" in html


def test_legends_button_and_handler_registered():
    pytest.importorskip("aiogram")
    from sqlalchemy import select  # noqa: F401  (кнопка проверяется ниже)

    from bot.keyboards.inline import main_menu_keyboard
    kb = main_menu_keyboard(has_character=True)
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "legends_hall" in datas, "в главном меню нужна кнопка летописи"

    from bot.handlers.world_extra import router
    from aiogram.types import CallbackQuery

    class _Probe:
        data = "legends_hall"

    found = False
    for handler in router.callback_query.handlers:
        for flt in handler.filters or []:
            try:
                if flt.callback(_Probe()):
                    found = True
            except Exception:
                continue
    assert found, "на кнопку «legends_hall» должен быть обработчик"
    assert CallbackQuery is not None


# ── напоминания ──────────────────────────────────────────────

async def _mk_lot(session, *, minutes_left=5, bidding=False,
                  seller_char=None, bidder_char=None):
    from datetime import timedelta

    from core.dates import utcnow

    item = Item(name=unique_name("Клинок"), description="тестовый предмет",
                item_type=ItemType.WEAPON, price=10)
    session.add(item)
    await session.flush()
    inst = ItemInstance(uid=f"REM{unique_id()}", item_id=item.id)
    session.add(inst)
    await session.flush()
    lot = AuctionLot(
        instance_id=inst.id, item_id=item.id,
        seller_id=seller_char.id if seller_char else None,
        seller_name=seller_char.name if seller_char else "",
        price=420, status=AuctionStatus.ACTIVE.value,
        expires_at=utcnow() + timedelta(minutes=minutes_left),
        start_bid=100 if bidding else 0,
        current_bid=150 if bidding else 0,
        current_bidder_id=bidder_char.id if (bidding and bidder_char) else None,
        current_bidder_name=bidder_char.name if (bidding and bidder_char) else "",
    )
    session.add(lot)
    await session.flush()
    return lot


@pytest.mark.asyncio
async def test_reminders_auction_end_notifies_seller_and_leader():
    from bot import reminders

    reminders.reset_dedup()
    async with async_session() as session:
        seller_user, seller = await _mk_hero(session)
        _, leader = await _mk_hero(session)
        lot = await _mk_lot(session, minutes_left=5, bidding=True,
                            seller_char=seller, bidder_char=leader)
        leader_user = await session.get(User, leader.user_id)
        far = await _mk_lot(session, minutes_left=120, seller_char=seller)
        due = await reminders.collect_due_reminders(session)

        tg_ids = [d["tg_id"] for d in due]
        texts = {d["tg_id"]: d["text"] for d in due}
        assert seller_user.telegram_id in tg_ids
        assert "закрываются" in texts[seller_user.telegram_id]
        assert leader_user.telegram_id in tg_ids, "лидер торгов — отдельная весточка"
        assert lot.id

        # «Далеко до финиша» — не пишем (лот far не попал ни одному адресату
        # повторно: сообщений про 120 минут в списке нет).
        assert all("120" not in t for t in texts.values())

        # Повторный проход за то же напоминание молчит (дедуп по лоту).
        due2 = await reminders.collect_due_reminders(session)
        assert all(d["tg_id"] not in (seller_user.telegram_id,
                                      leader_user.telegram_id) for d in due2)
        await session.rollback()


@pytest.mark.asyncio
async def test_reminders_portal_closing_broadcast():
    from bot import reminders
    from core.dungeons import PORTAL_MAX_LIFETIME
    from datetime import timedelta

    from core.dates import utcnow

    reminders.reset_dedup()
    async with async_session() as session:
        tpl = DungeonTemplate(name=unique_name("Крипта"),
                              portal_opened_at=utcnow() - (PORTAL_MAX_LIFETIME
                                                           - timedelta(minutes=7)),
                              portal_closed_at=None)
        session.add(tpl)
        await session.flush()
        due = await reminders.collect_due_reminders(session)
        casts = [d for d in due if d.get("broadcast")]
        assert any("Портал закрывается" in d["text"] for d in casts)
        assert not any("закрыт" in d.get("text", "") and not d.get("broadcast")
                       for d in due)
        due2 = await reminders.collect_due_reminders(session)
        assert [d for d in due2 if d.get("broadcast")] == [] or \
               all(d["text"] != casts[0]["text"] for d in due2 if d.get("broadcast")) \
            if casts else True
        await session.rollback()


@pytest.mark.asyncio
async def test_reminders_stale_duel_invite():
    pytest.importorskip("aiogram")
    from bot import reminders
    from bot.handlers.world_extra import duel_invites

    reminders.reset_dedup()
    async with async_session() as session:
        defender_user, defender = await _mk_hero(session)
        key = defender.id
        duel_invites[key] = (999000111, 100, time.time() - 200)  # висит 3+ мин
        try:
            due = await reminders.collect_due_reminders(session)
            mine = [d for d in due if d.get("tg_id") == defender_user.telegram_id]
            assert mine and "дуэль" in mine[0]["text"].lower()

            due2 = await reminders.collect_due_reminders(session)
            assert not [d for d in due2
                        if d.get("tg_id") == defender_user.telegram_id]
        finally:
            duel_invites.pop(key, None)
        # Свежий вызов (меньше двух минут) — не напоминаем.
        reminders.reset_dedup()
        duel_invites[key] = (999000111, 0, time.time())
        try:
            due3 = await reminders.collect_due_reminders(session)
            assert not [d for d in due3
                        if d.get("tg_id") == defender_user.telegram_id]
        finally:
            duel_invites.pop(key, None)
        await session.rollback()
