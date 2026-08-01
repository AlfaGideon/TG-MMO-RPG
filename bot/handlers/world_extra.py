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
from bot.keyboards.inline import continue_keyboard, main_menu_keyboard
from bot.utils.edit import safe_edit_text

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
    """Итог мирового действия: вернуться к прогулке, а не в меню.

    Диковины и надгробия находят прямо на клетке — выбрасывать после них
    игрока в главное меню значит обрывать вылазку на полпути.
    """
    return continue_keyboard()


def _menu_keyboard():
    """Для экранов, открытых из меню (репутация): назад в меню."""
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

        from core import factions as core_factions
        my_faction = core_factions.allegiance(character)
        my_rep = core_factions.value(character, my_faction) if my_faction else 0

        # Load current leader
        leader_id = None
        if my_faction:
            from core.models import AppSetting
            leader_row = await session.scalar(
                select(AppSetting).where(AppSetting.key == f"faction_leader_{my_faction}")
            )
            if leader_row and leader_row.value:
                leader_id = int(leader_row.value)

        leader_name = "Никто"
        if leader_id:
            leader_char = await session.get(Character, leader_id)
            if leader_char:
                leader_name = leader_char.name

        text = core_factions.card_text(character)

        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()

        if my_faction:
            text += f"\n\n👑 <b>Лидер твоей фракции:</b> {leader_name}"
            is_leader = (leader_id == character.id)
            if is_leader:
                text += " <i>(Ты являешься лидером этой фракции! 👑)</i>"
            elif my_rep >= 300:
                builder.button(text="👑 Стать лидером фракции (50k🪙)", callback_data=f"become_leader:{my_faction}")

        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(1)

    await safe_edit_text(
        callback,
        text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("become_leader:"))
async def become_leader_callback(callback: CallbackQuery):
    faction_key = callback.data.split(":")[1]

    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if character is None:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        from core import factions as core_factions
        my_faction = core_factions.allegiance(character)
        if my_faction != faction_key:
            await callback.answer("Вы не принадлежите к этой фракции!", show_alert=True)
            return

        my_rep = core_factions.value(character, my_faction)
        if my_rep < 300:
            await callback.answer("Требуется максимальная репутация (300)!", show_alert=True)
            return

        from engine.currency import total_in_bronze, deduct_currency
        if total_in_bronze(character) < 50000:
            await callback.answer("Недостаточно средств! Требуется 50,000🪙 (бронзы).", show_alert=True)
            return

        # Deduct currency
        deduct_currency(character, 50000)

        # Set leader in settings
        from core.models import AppSetting
        leader_row = await session.scalar(
            select(AppSetting).where(AppSetting.key == f"faction_leader_{faction_key}")
        )
        if not leader_row:
            leader_row = AppSetting(key=f"faction_leader_{faction_key}", value=str(character.id))
            session.add(leader_row)
        else:
            leader_row.value = str(character.id)

        await session.commit()

    await callback.answer("Поздравляем! Вы стали Лидером фракции! 👑", show_alert=True)
    await reputation(callback)


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
    await safe_edit_text(
        callback,
        text,
        reply_markup=_back_keyboard(),
        parse_mode="HTML",
    )


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
    await safe_edit_text(
        callback,
        "\n".join(lines),
        reply_markup=_back_keyboard(),
        parse_mode="HTML",
    )


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
            await safe_edit_text(
                callback,
                "🏰 <b>Мировой босс</b>\n\n<i>Сейчас в мире тихо.</i>",
                reply_markup=_back_keyboard(),
                parse_mode="HTML",
            )
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
    await safe_edit_text(
        callback,
        text,
        reply_markup=_boss_keyboard(can_hit),
        parse_mode="HTML",
    )


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
        await safe_edit_text(
            callback,
            "🏆 <b>Босс повержен!</b>\n\n<i>Награды разошлись всем, кто бился.</i>",
            reply_markup=_back_keyboard(),
            parse_mode="HTML",
        )
        return
    await callback.answer(f"Ты нанёс {dealt}. Получил {back}. Осталось {left}.")
    await world_boss(callback)
