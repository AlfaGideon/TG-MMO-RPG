from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.database import async_session
from core.models import User, Character, Location, Cell
from bot.keyboards.inline import locations_keyboard, cell_movement_keyboard, main_menu_keyboard, back_to_main_keyboard
from bot.utils.texts import location_text, cell_text, mini_map

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
            .options(selectinload(Character.location), selectinload(Character.cell))
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
        # Spawn at center (5,5)
        result = await session.execute(
            select(Cell).where(Cell.location_id == new_loc.id).where(Cell.x == 5).where(Cell.y == 5)
        )
        spawn_cell = result.scalar_one_or_none()
        if spawn_cell:
            character.cell_id = spawn_cell.id
        await session.commit()

        await show_cell(callback, character, new_loc, session)


@router.callback_query(F.data.startswith("move:"))
async def move_direction(callback: CallbackQuery):
    direction = callback.data.split(":")[1]
    dx, dy = {"north": (-1, 0), "south": (1, 0), "west": (0, -1), "east": (0, 1)}.get(direction, (0, 0))

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        result = await session.execute(
            select(Character)
            .where(Character.user_id == user.id)
            .options(selectinload(Character.location), selectinload(Character.cell))
        )
        character = result.scalar_one_or_none()
        if not character or not character.cell:
            await callback.answer("Ошибка перемещения.", show_alert=True)
            return

        current = character.cell
        new_x, new_y = current.x + dx, current.y + dy

        result = await session.execute(
            select(Cell)
            .where(Cell.location_id == character.location_id)
            .where(Cell.x == new_x)
            .where(Cell.y == new_y)
        )
        target = result.scalar_one_or_none()
        if not target or not target.is_passable:
            await callback.answer("Туда нельзя пройти!", show_alert=True)
            return

        character.cell_id = target.id
        await session.commit()
        await show_cell(callback, character, character.location, session)


@router.callback_query(F.data == "show_map")
async def show_map(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        result = await session.execute(
            select(Character)
            .where(Character.user_id == user.id)
            .options(selectinload(Character.cell))
        )
        character = result.scalar_one_or_none()
        if not character or not character.cell:
            await callback.answer("Ошибка.", show_alert=True)
            return

        result = await session.execute(
            select(Cell).where(Cell.location_id == character.location_id)
        )
        cells = result.scalars().all()

        map_text = mini_map(cells, character.cell.x, character.cell.y)
        await callback.message.edit_text(
            f"🗺 <b>Мини-карта</b>\n{map_text}\n\n🧙 — ты | 👾 — враг | 🌲 — проходимо | ⬛ — непроходимо",
            reply_markup=back_to_main_keyboard(),
            parse_mode="HTML",
        )


async def show_cell(callback, character, location, session):
    cell = character.cell
    if not cell:
        await callback.message.edit_text(
            location_text(location),
            reply_markup=main_menu_keyboard(has_character=True),
            parse_mode="HTML",
        )
        return

    # Check neighbors
    neighbors = {}
    for direction, (dx, dy) in {"north": (-1, 0), "south": (1, 0), "west": (0, -1), "east": (0, 1)}.items():
        result = await session.execute(
            select(Cell)
            .where(Cell.location_id == location.id)
            .where(Cell.x == cell.x + dx)
            .where(Cell.y == cell.y + dy)
        )
        n = result.scalar_one_or_none()
        neighbors[direction] = n is not None and n.is_passable

    has_mob = cell.mob_id is not None

    text = cell_text(cell, location.name)
    if cell.image_url:
        # If we have an image, send it as photo with caption
        try:
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=cell.image_url,
                caption=text,
                reply_markup=cell_movement_keyboard(
                    neighbors["north"], neighbors["south"],
                    neighbors["west"], neighbors["east"], has_mob
                ),
                parse_mode="HTML",
            )
            return
        except Exception:
            pass

    await callback.message.edit_text(
        text,
        reply_markup=cell_movement_keyboard(
            neighbors["north"], neighbors["south"],
            neighbors["west"], neighbors["east"], has_mob
        ),
        parse_mode="HTML",
    )
