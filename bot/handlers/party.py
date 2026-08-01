from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.database import async_session
from core.models import User, Character, Party
from bot.keyboards.inline import main_menu_keyboard, back_to_main_keyboard
from bot.utils.edit import safe_edit_text

router = Router()


@router.callback_query(F.data == "party_menu")
async def party_menu(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        result = await session.execute(
            select(Character)
            .where(Character.user_id == user.id)
            .options(selectinload(Character.party))
        )
        character = result.scalar_one_or_none()
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        if character.party:
            party = character.party
            result = await session.execute(
                select(Character).where(Character.party_id == party.id).options(selectinload(Character.user))
            )
            members = result.scalars().all()
            lines = [f"👥 <b>Пати: {party.name}</b>\n"]
            for m in members:
                leader = "👑" if m.id == party.leader_id else ""
                lines.append(f"{leader} {m.name} (ур. {m.level})")
            text = "\n".join(lines)
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            builder = InlineKeyboardBuilder()
            builder.button(text="🚪 Выйти из пати", callback_data="party_leave")
            builder.button(text="◀️ Назад", callback_data="main_menu")
            builder.adjust(1)
            await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode="HTML")
        else:
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            builder = InlineKeyboardBuilder()
            builder.button(text="➕ Создать пати", callback_data="party_create")
            builder.button(text="◀️ Назад", callback_data="main_menu")
            builder.adjust(1)
            await safe_edit_text(callback, "👥 <b>Пати</b>\n\nТы не состоишь в пати.\n\n"
                "Создай свою или попроси друга пригласить тебя.",
                reply_markup=builder.as_markup(),
                parse_mode="HTML",
            )


@router.callback_query(F.data == "party_create")
async def party_create(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        result = await session.execute(
            select(Character).where(Character.user_id == user.id)
        )
        character = result.scalar_one_or_none()

        if character.party_id:
            await callback.answer("Ты уже в пати!", show_alert=True)
            return

        party = Party(name=f"Отряд {character.name}", leader_id=character.id)
        session.add(party)
        await session.flush()
        character.party_id = party.id
        await session.commit()

    await callback.answer("Пати создано!")
    await party_menu(callback)


@router.callback_query(F.data == "party_leave")
async def party_leave(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        result = await session.execute(
            select(Character).where(Character.user_id == user.id)
        )
        character = result.scalar_one_or_none()

        if not character.party_id:
            await callback.answer("Ты не в пати.", show_alert=True)
            return

        party = await session.get(Party, character.party_id)
        character.party_id = None
        await session.commit()

        # If leader leaves, disband or transfer
        if party and party.leader_id == character.id:
            result = await session.execute(
                select(Character).where(Character.party_id == party.id)
            )
            remaining = result.scalars().all()
            if remaining:
                party.leader_id = remaining[0].id
            else:
                await session.delete(party)
        await session.commit()

    await callback.answer("Ты покинул пати.")
    await party_menu(callback)
