from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.database import async_session
from core.models import User, Character, Location
from bot.keyboards.inline import locations_keyboard, main_menu_keyboard, back_to_main_keyboard
from bot.utils.texts import location_text

router = Router()


@router.callback_query(F.data == "locations")
async def locations(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        result = await session.execute(
            select(Character).where(Character.user_id == user.id)
        )
        character = result.scalar_one_or_none()
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        result = await session.execute(select(Location).order_by(Location.min_level))
        locs = result.scalars().all()

        await callback.message.edit_text(
            "🗺 <b>Локации</b>\n\nВыбери, куда отправиться:",
            reply_markup=locations_keyboard(locs, character.location_id),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("travel:"))
async def travel(callback: CallbackQuery):
    loc_id = int(callback.data.split(":")[1])
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
            .options(selectinload(Character.location))
        )
        character = result.scalar_one_or_none()
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        result = await session.execute(select(Location).where(Location.id == loc_id))
        new_loc = result.scalar_one_or_none()
        if not new_loc:
            await callback.answer("Локация не найдена.", show_alert=True)
            return

        if character.level < new_loc.min_level:
            await callback.answer(
                f"Нужен {new_loc.min_level} уровень!", show_alert=True
            )
            return

        character.location_id = new_loc.id
        await session.commit()

        await callback.message.edit_text(
            location_text(new_loc),
            reply_markup=main_menu_keyboard(has_character=True),
            parse_mode="HTML",
        )
