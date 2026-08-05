from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from core.database import async_session
from core.models import User, Character, Quest, CharacterQuest
from core.quests import available_quests, active_quests, take_quest, complete_quest, check_deliver
from bot.keyboards.inline import continue_keyboard, main_menu_keyboard
from bot.utils.edit import safe_edit_text
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()


@router.callback_query(F.data == "quests")
async def quest_journal(callback: CallbackQuery):
    """Дневник заданий."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        character = (await session.execute(
            select(Character).where(Character.user_id == user.id)
        )).scalar_one_or_none()
        
        if not character:
            await callback.answer("Сначала создай героя.", show_alert=True)
            return

        active = await active_quests(session, character)
        
        lines = ["📜 <b>Дневник заданий</b>\n"]
        builder = InlineKeyboardBuilder()
        
        if not active:
            lines.append("<i>У тебя пока нет активных заданий. Поговори с жителями в поселениях.</i>")
        else:
            for cq in active:
                quest = cq.quest
                is_ready = await check_deliver(session, character, cq)
                mark = "✅" if is_ready else "▫️"
                
                goal = ""
                if quest.objective_type == "kill":
                    goal = f"Убить {quest.objective_target}: {cq.progress}/{quest.objective_count}"
                elif quest.objective_type == "reach":
                    goal = f"Разведать локацию: {'выполнено' if cq.progress >= 1 else 'в пути'}"
                elif quest.objective_type == "collect":
                    goal = f"Собрать {quest.objective_target}: {cq.progress}/{quest.objective_count}"
                
                lines.append(f"{mark} <b>{quest.name}</b>\n└ {goal}")
                
                if is_ready:
                    builder.button(text=f"✅ Сдать: {quest.name[:15]}", callback_data=f"q_finish:{quest.id}")
                else:
                    builder.button(text=f"❌ Бросить: {quest.name[:15]}", callback_data=f"q_drop:{quest.id}")
        
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(1)
        
        await safe_edit_text(callback, "\n".join(lines), reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("q_take:"))
async def q_take_handler(callback: CallbackQuery):
    quest_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalar_one_or_none()
        character = (await session.execute(select(Character).where(Character.user_id == user.id))).scalar_one_or_none()
        
        ok, msg = await take_quest(session, character, quest_id)
        await callback.answer(msg, show_alert=True)
        if ok:
            await quest_journal(callback)


@router.callback_query(F.data.startswith("q_finish:"))
async def q_finish_handler(callback: CallbackQuery):
    quest_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalar_one_or_none()
        character = (await session.execute(select(Character).where(Character.user_id == user.id))).scalar_one_or_none()
        
        ok, msg = await complete_quest(session, character, quest_id)
        await callback.answer("Задание выполнено!" if ok else msg, show_alert=True)
        if ok:
            await safe_edit_text(callback, msg, reply_markup=continue_keyboard(), parse_mode="HTML")


@router.callback_query(F.data.startswith("q_drop:"))
async def q_drop_handler(callback: CallbackQuery):
    quest_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalar_one_or_none()
        character = (await session.execute(select(Character).where(Character.user_id == user.id))).scalar_one_or_none()
        
        await session.execute(
            update(CharacterQuest)
            .where(CharacterQuest.character_id == character.id)
            .where(CharacterQuest.quest_id == quest_id)
            .values(status="failed")
        )
        await session.commit()
    await callback.answer("Задание отменено.")
    await quest_journal(callback)
