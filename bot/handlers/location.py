from aiogram import Router, F
from aiogram.types import CallbackQuery, FSInputFile
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.database import async_session
from core.models import User, Character, Location, Cell
from core.map_renderer import ensure_cell_image
from bot.keyboards.inline import (
    cell_movement_keyboard, inspect_keyboard,
    main_menu_keyboard, back_to_main_keyboard
)
from bot.utils.texts import location_text, cell_text

router = Router()

EMPTY_INSPECT_LINES = [
    "Ты осматриваешься, но ничего примечательного не находишь. Лишь ветер шевелит травы.",
    "Здесь пусто. Даже следы чужих ботинок редки в этих местах.",
    "Ты прислушиваешься... Тишина. Полная, глухая тишина.",
    "Осмотр не выявил ничего интересного. Только твоя тень сопровождает тебя.",
    "Пустошь. Ни души, ни сокровищ — лишь пепел и пыль.",
    "Ты ощупал каждый камень. Ничего. Даже вороны облетели эту клетку стороной.",
    "Здесь когда-то что-то было... теперь лишь пустота и эхо прошлого.",
    "Ты внимательно осмотрелся. Увы, удача сегодня не на твоей стороне.",
    "Ни врагов, ни друзей, ни сокровищ. Сплошное безмолвие.",
    "Ты присел на корточки и изучил землю. Ничего, кроме следов дождя.",
    "Воздух здесь странно чист. Слишком чист. Как будто всё живое исчезло.",
    "Ты осторожно обошёл кусты. Пусто. Даже грибов нет.",
    "Осмотр клетки принёс разочарование: ни монстров, ни NPC, ни сундуков.",
    "Здесь нет ничего, кроме твоих собственных мыслей. И они тревожны...",
    "Ты нашёл лишь старый окурок и потрескавшийся камень. Больше ничего.",
]


@router.callback_query(F.data.startswith("move:"))
async def move_direction(callback: CallbackQuery):
    direction = callback.data.split(":")[1]
    deltas = {
        "north": (-1, 0), "south": (1, 0), "west": (0, -1), "east": (0, 1),
        "nw": (-1, -1), "ne": (-1, 1), "sw": (1, -1), "se": (1, 1),
    }
    dx, dy = deltas.get(direction, (0, 0))

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

        # Check seamless transition
        if target.target_location_id is not None and target.target_x is not None and target.target_y is not None:
            result = await session.execute(
                select(Cell)
                .where(Cell.location_id == target.target_location_id)
                .where(Cell.x == target.target_x)
                .where(Cell.y == target.target_y)
            )
            dest_cell = result.scalar_one_or_none()
            if dest_cell:
                character.location_id = target.target_location_id
                character.cell_id = dest_cell.id
                await session.commit()
                await show_cell(callback, character, dest_cell.location, session)
                return

        character.cell_id = target.id
        await session.commit()
        await show_cell(callback, character, character.location, session)


@router.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery):
    await callback.answer("Туда нельзя пройти.", show_alert=True)


@router.callback_query(F.data == "inspect")
async def inspect_cell(callback: CallbackQuery):
    import random
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        result = await session.execute(
            select(Character)
            .where(Character.user_id == user.id)
            .options(selectinload(Character.cell).selectinload(Cell.mob))
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
            lines.append(f"\n<i>{random.choice(EMPTY_INSPECT_LINES)}</i>")

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

    can_dirs = {}
    for direction, (dx, dy) in {
        "north": (-1, 0), "south": (1, 0), "west": (0, -1), "east": (0, 1),
        "nw": (-1, -1), "ne": (-1, 1), "sw": (1, -1), "se": (1, 1),
    }.items():
        result = await session.execute(
            select(Cell)
            .where(Cell.location_id == location.id)
            .where(Cell.x == cell.x + dx)
            .where(Cell.y == cell.y + dy)
        )
        n = result.scalar_one_or_none()
        can_dirs[direction] = n is not None and n.is_passable

    text = cell_text(cell, location.name)

    result = await session.execute(
        select(Cell).where(Cell.location_id == location.id)
    )
    cells = result.scalars().all()

    img_path = ensure_cell_image(cell, cells, cell.x, cell.y)
    kb = cell_movement_keyboard(can_dirs)

    if callback.message.photo:
        try:
            from aiogram.types import InputMediaPhoto
            await callback.message.edit_media(
                media=InputMediaPhoto(media=FSInputFile(img_path), caption=text, parse_mode="HTML"),
                reply_markup=kb,
            )
            return
        except Exception:
            pass

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
