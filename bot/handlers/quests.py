"""Задания в боте: доска, взятие и сдача.

Долг реестра паритета: модели `Quest`/`CharacterQuest` и три задания в
сиде существовали, но в боте не было ни выдачи, ни сдачи — игрок не мог
взять ни одного. Правила живут в `core/quests.py`, здесь только экраны.
"""
from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from core import quests as core_quests
from core.database import async_session
from core.models import Character, User
from bot.keyboards.inline import continue_keyboard
from bot.utils.edit import safe_edit_text

router = Router()


async def _character(session, telegram_id: int):
    result = await session.execute(
        select(Character).join(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


@router.callback_query(F.data == "quests_menu")
async def quests_menu(callback: CallbackQuery):
    """📜 Задания: что взято и что можно взять."""
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        active = await core_quests.active_for(session, character)
        available = await core_quests.available_for(session, character)

        lines = ["📜 <b>Задания</b>", ""]
        builder = InlineKeyboardBuilder()

        if active:
            lines.append("<b>В работе:</b>")
            for cq in active:
                quest = cq.quest
                if quest is None:
                    continue
                need = max(1, quest.objective_count or 1)
                have = await core_quests.progress_of(session, character, cq)
                done = have >= need
                mark = "✅" if done else "⏳"
                lines.append(f"{mark} <b>{quest.name}</b> — {have}/{need}")
                lines.append(f"   <i>{quest.description}</i>")
                if done:
                    builder.button(text=f"✅ Сдать: {quest.name}",
                                   callback_data=f"quest_turnin:{cq.id}")
            lines.append("")

        if available:
            lines.append("<b>Доступны:</b>")
            for quest in available[:6]:
                reward = []
                if quest.reward_gold:
                    reward.append(f"{quest.reward_gold}🟤")
                if quest.reward_exp:
                    reward.append(f"{quest.reward_exp}⭐")
                lines.append(f"• <b>{quest.name}</b> — {', '.join(reward) or 'без награды'}")
                lines.append(f"   <i>{quest.description}</i>")
                builder.button(text=f"📜 Взять: {quest.name}",
                               callback_data=f"quest_take:{quest.id}")
        elif not active:
            lines.append("<i>Заданий пока нет — возвращайся, когда подрастёшь.</i>")

        builder.button(text="◀️ Меню", callback_data="main_menu")
        builder.adjust(1)

    await safe_edit_text(callback, "\n".join(lines),
                         reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("quest_take:"))
async def quest_take(callback: CallbackQuery):
    """Взять задание."""
    quest_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        res = await core_quests.accept(session, character, quest_id)
        if not res["ok"]:
            await callback.answer(res["reason"], show_alert=True)
            return
        await session.commit()
        name = res["quest"].name

    await callback.answer(f"📜 Задание «{name}» принято!", show_alert=True)
    await quests_menu(callback)


@router.callback_query(F.data.startswith("quest_turnin:"))
async def quest_turnin(callback: CallbackQuery):
    """Сдать выполненное задание."""
    cq_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        res = await core_quests.turn_in(session, character, cq_id)
        if not res["ok"]:
            await callback.answer(res["reason"], show_alert=True)
            return
        await session.commit()

    reward = [f"🟤 +{res['gold']}"] if res["gold"] else []
    if res["exp"]:
        reward.append(f"⭐ +{res['exp']}")
    if res["item"]:
        reward.append(f"🎁 {res['item']}")

    await safe_edit_text(
        callback,
        f"✅ <b>{res['name']}</b> — выполнено!\n\n"
        f"{'   '.join(reward) if reward else 'Награды нет.'}{res['note']}",
        reply_markup=continue_keyboard(),
        parse_mode="HTML",
    )
