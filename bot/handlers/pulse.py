"""🩸 Пульс героя — серверный экран (паритет с engine/pulse.py).

Собирает в один текст то, что игрок иначе искал бы между «Профилем»,
«Заданиями», «Знамениями» и «Картой»: здоровье/ману, валюту, активные
задания, живые события мира, луну, дом и личную карту сокровищ.
"""
from datetime import datetime

from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from bot.keyboards.inline import pulse_keyboard
from bot.utils.edit import safe_edit_text
from bot.utils.texts import _bar, currency_str
from core import karma as core_karma
from core import lunar as core_lunar
from core import quests as core_quests
from core import worldevents as WE
from core.database import async_session
from core.models import Battle, Character, InventoryItem, Location, User
from core.stats import combat_stats
from core.vip import is_vip_active

router = Router()

TASKS_SHOWN = 3


def _tz_naive(dt):
    if dt is None:
        return None
    if hasattr(dt, "tzinfo") and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def _left(dt) -> str:
    until = _tz_naive(dt)
    if until is None:
        return "?"
    left = int((until - datetime.now()).total_seconds())
    if left <= 0:
        return "скоро"
    mins = max(0, left // 60)
    if mins >= 60:
        return f"{mins // 60}ч {mins % 60}м"
    return f"{mins}м"


def _faction_name(key: str) -> str:
    from core import factions as F
    return (F.FACTIONS.get(key) or (None, key))[1] or key


async def _active_tasks(session, character):
    lines = []
    cqs = await core_quests.active_for(session, character)
    for cq in cqs[:TASKS_SHOWN]:
        quest = cq.quest
        if quest is None:
            continue
        n = await core_quests.progress_of(session, character, cq)
        need = max(1, quest.objective_count or 1)
        mark = "✅" if n >= need else "▫️"
        lines.append(f"{mark} <b>{quest.name}</b> · {n}/{need}")
    if len(cqs) > TASKS_SHOWN:
        lines.append(f"…и ещё {len(cqs) - TASKS_SHOWN} задание(я) — открой 📜 Дневник.")
    return lines


async def _event_lines(session, character):
    lines = []
    phase = await core_lunar.get_phase(session)
    if phase:
        lines.append(f"{phase['name']} · {phase['desc']}")
    for ev in await WE.active_cataclysms(session, character.location_id):
        from core.worldevents import KINDS, title
        k = KINDS.get(ev.key) or {}
        where = "весь мир" if ev.is_global else await _loc_name(session, ev.location_id)
        lines.append(f"{title('cataclysm', ev.key)} · {where} · "
                     f"ещё {_left(ev.until)}")
    boss = await WE.active_boss(session)
    if boss:
        loc = await _loc_name(session, boss.location_id)
        lines.append(f"{WE.title('boss', boss.key)} · {loc} · "
                     f"❤️ {boss.hp}/{boss.max_hp} · ещё {_left(boss.until)}")
    for s in await WE.active_sieges(session, character.location_id):
        atk = s.key.split("siege_", 1)[-1] if s.key.startswith("siege_") else "?"
        place = await _loc_name(session, s.location_id)
        lines.append(f"🔥 {_faction_name(atk)} · {place} · "
                     f"ворота {s.hp}/{s.max_hp} · ещё {_left(s.until)}")
    return lines


async def _loc_name(session, location_id):
    if location_id is None:
        return "весь мир"
    row = await session.get(Location, location_id)
    return row.name if row else "?"


async def _home_line(session, character):
    if not (character.house_level or 0):
        return ""
    home_count = await session.scalar(
        select(func.count(InventoryItem.id))
        .where(InventoryItem.character_id == character.id)
        .where(InventoryItem.in_home == True)  # noqa: E712
    ) or 0
    at = ""
    if character.home_location_id == character.location_id:
        at = " · ты дома"
    return (f"🏠 Дом ур. {character.house_level} · сундук {home_count} · "
            f"локация {character.home_location_id}{at}")


def _goal_lines(character):
    out = []
    coord = getattr(character, "treasure_map_coord", None) or ""
    if coord:
        out.append(f"📜 Карта сокровищ: {coord}")
    return out


@router.callback_query(F.data == "pulse")
async def pulse(callback: CallbackQuery):
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()
        if user is None:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        character = (await session.execute(
            select(Character)
            .where(Character.user_id == user.id)
            .options(selectinload(Character.location),
                     selectinload(Character.cell),
                     selectinload(Character.party))
        )).scalar_one_or_none()
        if character is None:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        cls_def = await _get_class(session, character)
        stats = await combat_stats(session, character)
        max_hp = stats.get("max_hp", getattr(character, "max_hp", 100))
        max_mp = stats.get("max_mp", getattr(character, "max_mp", 50))

        lines = [
            f"🩸 <b>Пульс героя</b>"
            f"{' 👑' if is_vip_active(character) else ''}",
            f"{cls_def.name if cls_def else character.character_class} · "
            f"ур. {character.level} · {currency_str(character)}",
            core_karma.karma_line(character),
            "",
            f"❤️ {character.current_hp}/{max_hp}",
            _bar(character.current_hp, max_hp, "🟥", "⬛"),
            f"💙 {character.current_mp}/{max_mp}",
            _bar(character.current_mp, max_mp, "🟦", "⬛"),
            f"⭐ {character.experience}/{character.level * 100}",
        ]

        tasks = await _active_tasks(session, character)
        if tasks:
            lines += ["", "📜 <b>Задания</b>", *tasks]

        events = await _event_lines(session, character)
        if events:
            lines += ["", "🌍 <b>Мир</b>", *events]

        goals = _goal_lines(character)
        if goals:
            lines += ["", "🧭 <b>Цели</b>", *goals]

        home = await _home_line(session, character)
        if home:
            lines += ["", home]

        loc = character.location.name if character.location else "Неизвестно"
        bag_count = await session.scalar(
            select(func.count(InventoryItem.id))
            .where(InventoryItem.character_id == character.id)
            .where(InventoryItem.in_stash == False)  # noqa: E712
            .where(InventoryItem.in_home == False)   # noqa: E712
        ) or 0
        stash_count = await session.scalar(
            select(func.count(InventoryItem.id))
            .where(InventoryItem.character_id == character.id)
            .where(InventoryItem.in_stash == True)  # noqa: E712
        ) or 0
        lines += [
            "",
            f"📍 Ты в: {loc}",
            f"🎒 Сумка {bag_count} · 🔒 {stash_count} · "
            f"☠️ Побед: {await _victories(session, character.id)}",
        ]

        boss = await WE.active_boss(session)
        sieges = await WE.active_sieges(session, character.location_id)
        markup = pulse_keyboard(has_boss=bool(boss), has_siege=bool(sieges))

    await safe_edit_text(callback, "\n".join(lines), reply_markup=markup)


async def _get_class(session, character):
    from core.classes import get_class
    return await get_class(session, character.character_class)


async def _victories(session, character_id):
    from core.enums import BattleResult
    return await session.scalar(
        select(func.count(Battle.id))
        .where(Battle.character_id == character_id)
        .where(Battle.result == BattleResult.VICTORY)
    ) or 0
