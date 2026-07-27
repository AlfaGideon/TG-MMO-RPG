from aiogram import Router, F
from aiogram.types import CallbackQuery, FSInputFile
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.database import async_session
from core.models import User, Character, Location, Cell
from core.map_renderer import ensure_cell_image
from bot.keyboards.inline import (
    locations_keyboard, cell_movement_keyboard, inspect_keyboard,
    main_menu_keyboard, back_to_main_keyboard
)
from bot.utils.texts import location_text, cell_text

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


@router.callback_query(F.data == "inspect")
async def inspect_cell(callback: CallbackQuery):
    """Player inspects current cell - reveals hidden elements."""
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

        cell = character.cell
        lines = [f"🔍 <b>Осмотр клетки [{cell.x},{cell.y}]</b>\n"]
        lines.append(f"<i>{cell.name}</i>\n")
        lines.append(f"{cell.description}\n")

        found = []
        if cell.mob_id:
            found.append(f"👾 Ты заметил врага: {cell.mob.name}!")
        if cell.has_npc:
            found.append(f"💬 Здесь кто-то есть: {cell.npc_name}")
        if cell.has_chest:
            found.append("📦 Ты нашёл сундук!")

        if found:
            lines.append("\n" + "\n".join(found))
        else:
            lines.append("\n<i>Ничего необычного.</i>")

        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=inspect_keyboard(
                has_mob=bool(cell.mob_id),
                has_npc=cell.has_npc,
                has_chest=cell.has_chest,
            ),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "back_to_cell")
async def back_to_cell(callback: CallbackQuery):
    """Return to cell view with image."""
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
        if character and character.cell:
            await show_cell(callback, character, character.location, session)


@router.callback_query(F.data == "talk_npc")
async def talk_npc(callback: CallbackQuery):
    """Talk to NPC - text only, no image."""
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
        if not character or not character.cell or not character.cell.has_npc:
            await callback.answer("Здесь никого нет.", show_alert=True)
            return

        cell = character.cell
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()

        if cell.npc_type == "merchant":
            builder.button(text="🛒 Торговать", callback_data="shop")
        builder.button(text="◀️ Назад", callback_data="back_to_cell")
        builder.adjust(1)

        await callback.message.edit_text(
            f"💬 <b>{cell.npc_name}</b>\n\n<i>{cell.npc_dialogue}</i>",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "open_chest")
async def open_chest(callback: CallbackQuery):
    """Open chest - simple reward for now."""
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
        if not character or not character.cell or not character.cell.has_chest:
            await callback.answer("Здесь нет сундука.", show_alert=True)
            return

        import random
        gold = random.randint(5, 25)
        character.gold += gold
        character.cell.has_chest = False
        await session.commit()

        await callback.message.edit_text(
            f"📦 <b>Сундук открыт!</b>\n\nВнутри ты нашёл {gold}🪙 золота.",
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

    text = cell_text(cell, location.name)

    # Get all cells for minimap
    result = await session.execute(
        select(Cell).where(Cell.location_id == location.id)
    )
    cells = result.scalars().all()

    # Generate cell image
    img_path = ensure_cell_image(cell, cells, cell.x, cell.y)

    # Build keyboard - no hints about mobs/NPCs
    kb = cell_movement_keyboard(
        neighbors["north"], neighbors["south"],
        neighbors["west"], neighbors["east"]
    )

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer_photo(
        photo=FSInputFile(img_path),
        caption=text,
        reply_markup=kb,
        parse_mode="HTML",
    )
