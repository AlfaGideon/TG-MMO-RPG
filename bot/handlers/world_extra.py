"""Репутация, надгробия, диковины и мировой босс — экраны бота.

Паритет с браузерным стеком: те же механики, что в `engine/factions.py`,
`engine/death.py`, `engine/landmarks.py` и `engine/worldboss.py`, только
поверх БД. Логика и числа берутся из общих модулей `core/*`.

Вынесено отдельным файлом, чтобы не раздувать location.py и battle.py.
"""
from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core import behavior as core_behavior
from core import death as core_death
from core import factions as core_factions
from core import landmarks as core_landmarks
from core import worldevents as core_events
from core.database import async_session
from core.models import Character, User
from bot.keyboards.inline import main_menu_keyboard

router = Router()


async def _character(session, telegram_id):
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        return None
    result = await session.execute(
        select(Character)
        .where(Character.user_id == user.id)
        .options(selectinload(Character.cell))
    )
    return result.scalar_one_or_none()


def _back_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Меню", callback_data="main_menu")
    return builder.as_markup()


# ── репутация ───────────────────────────────────────────────

@router.callback_query(F.data == "reputation")
async def reputation(callback: CallbackQuery):
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if character is None:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        text = core_factions.card_text(character)
    await callback.message.edit_text(text, reply_markup=_back_keyboard(),
                                     parse_mode="HTML")


# ── надгробия ───────────────────────────────────────────────

@router.callback_query(F.data == "claim_grave")
async def claim_grave(callback: CallbackQuery):
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if character is None or character.cell is None:
            await callback.answer("Ошибка.", show_alert=True)
            return
        cell = character.cell
        grave = await core_death.at(session, cell.location_id, cell.x, cell.y,
                                    floor=cell.floor or 0)
        if grave is None:
            await callback.answer("Здесь нечего забирать.", show_alert=True)
            return
        gold, items, own = await core_death.claim(session, character, grave)
        if not own:
            core_factions.award(character, "grave_looted")
        await session.commit()

    got = [f"+{gold} 🪙"] if gold else []
    if items:
        got.append(f"🎒 вещей: {len(items)}")
    body = ", ".join(got) if got else "здесь уже пусто"
    if own:
        text = (f"🪦 <b>Ты вернулся за своим.</b>\n\n{body}\n\n"
                f"<i>Земля отпускает то, что взяла.</i>")
    else:
        text = (f"🪦 <b>Чужая могила</b>\n\nТы забрал: {body}\n\n"
                f"<i>Половина рассыпалась прахом — мародёрство не в чести.</i>")
    await callback.message.edit_text(text, reply_markup=_back_keyboard(),
                                     parse_mode="HTML")


# ── достопримечательности ───────────────────────────────────

@router.callback_query(F.data == "study_landmark")
async def study_landmark(callback: CallbackQuery):
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if character is None or character.cell is None:
            await callback.answer("Ошибка.", show_alert=True)
            return
        ok, lines = await core_landmarks.claim(session, character,
                                               character.cell)
        if not ok:
            await callback.answer(lines[0], show_alert=True)
            return
        await session.commit()
    await callback.message.edit_text("\n".join(lines),
                                     reply_markup=_back_keyboard(),
                                     parse_mode="HTML")


# ── мировой босс ────────────────────────────────────────────

def _boss_keyboard(can_hit):
    builder = InlineKeyboardBuilder()
    if can_hit:
        builder.button(text="⚔️ Ударить", callback_data="boss_hit")
    builder.button(text="🔄 Обновить", callback_data="world_boss")
    builder.button(text="◀️ Меню", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


@router.callback_query(F.data == "world_boss")
async def world_boss(callback: CallbackQuery):
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if character is None:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        ev = await core_events.active_boss(session)
        if ev is None:
            await callback.message.edit_text(
                "🏰 <b>Мировой босс</b>\n\n<i>Сейчас в мире тихо.</i>",
                reply_markup=_back_keyboard(), parse_mode="HTML")
            return
        b = core_events.BOSSES[ev.key]
        share = await core_events.boss_contribution(session, ev, character)
        here = character.location_id == ev.location_id
        can_hit = here and character.level >= b["level"]
        text = (
            f"{core_events.title('boss', ev.key)}\n<i>{b['story']}</i>\n\n"
            f"❤️ {ev.hp}/{ev.max_hp}\n"
            f"👥 твой вклад: {int(share * 100)}%\n"
        )
        if ev.phase:
            text += "\n🔥 <i>Вторая фаза: босс призвал свиту.</i>"
        if not here:
            text += "\n⚠️ <i>Ты не в той локации.</i>"
        elif character.level < b["level"]:
            text += f"\n⚠️ <i>Нужен {b['level']} уровень.</i>"
        await session.commit()
    await callback.message.edit_text(text, reply_markup=_boss_keyboard(can_hit),
                                     parse_mode="HTML")


@router.callback_query(F.data == "boss_hit")
async def boss_hit(callback: CallbackQuery):
    import random

    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        ev = await core_events.active_boss(session)
        if character is None or ev is None:
            await callback.answer("Босса уже нет.", show_alert=True)
            return
        b = core_events.BOSSES[ev.key]
        if character.location_id != ev.location_id:
            await callback.answer("Босс не здесь.", show_alert=True)
            return
        if character.level < b["level"]:
            await callback.answer(f"Нужен {b['level']} уровень.", show_alert=True)
            return

        dealt = max(1, character.strength * 2 + random.randint(0, 10)
                    - b["defense"])
        left, phased = await core_events.hit_boss(session, character, dealt)
        back = max(0, int(b["damage"] * random.uniform(0.5, 1.0))
                   - character.endurance // 3)
        character.current_hp = max(1, character.current_hp - back)
        await session.commit()

    if left <= 0:
        await callback.message.edit_text(
            "🏆 <b>Босс повержен!</b>\n\n<i>Награды разошлись всем, кто бился.</i>",
            reply_markup=_back_keyboard(), parse_mode="HTML")
        return
    await callback.answer(f"Ты нанёс {dealt}. Получил {back}. Осталось {left}.")
    await world_boss(callback)
