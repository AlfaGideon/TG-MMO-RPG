from aiogram import Router, F
from aiogram.types import CallbackQuery, FSInputFile
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from datetime import datetime, timedelta

from core.database import async_session
from core.loot import give_chest_loot
from core.models import User, Character, Location, Cell, VisitedCell
from core.spawns import spawn_at_cell
from core.map_renderer import ensure_cell_image, render_player_map, get_player_map_path
from bot.keyboards.inline import (
    cell_movement_keyboard, inspect_keyboard,
    main_menu_keyboard, back_to_main_keyboard, map_view_keyboard,
    travel_keyboard,
)
from bot.utils.texts import location_text, cell_text, loot_text
from bot.utils.photos import send_or_edit_photo, get_photo_input

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

DIRECTIONS = {
    "n": (-1, 0), "s": (1, 0), "w": (0, -1), "e": (0, 1),
    "nw": (-1, -1), "ne": (-1, 1), "sw": (1, -1), "se": (1, 1),
}
# Backward-compatible aliases for any old callback data / admin tooling.
DIRECTION_ALIASES = {
    "north": "n", "south": "s", "west": "w", "east": "e",
}
DIRECTION_ARROWS = {
    "n": "⬆️", "s": "⬇️", "w": "⬅️", "e": "➡️",
    "nw": "↖️", "ne": "↗️", "sw": "↙️", "se": "↘️",
}


def _current_transition(cell: Cell, location: Location):
    """Button label + text hint for transition located on the current cell.

    Movement arrows show transitions on neighboring cells, but when a player
    already stands on a stair/door cell (common after adding floors to the
    стартовая локация), they need an explicit action button.
    """
    if (
        cell is None
        or cell.target_location_id is None
        or cell.target_x is None
        or cell.target_y is None
    ):
        return None, None

    target_floor = cell.target_floor if cell.target_floor is not None else 0
    current_floor = cell.floor or 0
    if cell.target_location_id == location.id:
        target_label = target_floor + 1
        if target_floor > current_floor:
            button = f"🪜⬆️ Подняться на этаж {target_label}"
            hint = f"🪜 <b>Лестница вверх:</b> можно подняться на этаж <b>{target_label}</b>."
        elif target_floor < current_floor:
            button = f"🪜⬇️ Спуститься на этаж {target_label}"
            hint = f"🪜 <b>Лестница вниз:</b> можно спуститься на этаж <b>{target_label}</b>."
        else:
            button = f"🪜 Перейти на этаж {target_label}"
            hint = f"🪜 <b>Переход:</b> ведёт на этаж <b>{target_label}</b>."
    else:
        button = "🚪 Перейти через дверь"
        hint = "🚪 <b>Дверь:</b> отсюда можно перейти в другую локацию."
    return button, hint


async def _ensure_floor_stairs_present(session, location: Location):
    """Lazy safety net for locations that were made multi-floor earlier.

    Admin resize creates stairs, but old/manual data can have floors_count > 1
    without enough floor links. On first player view we restore the standard
    stair pair near the center so floors are reachable in-game.
    """
    floors = max(1, location.floors_count or 1)
    if floors < 2:
        return
    expected_links = 2 * (floors - 1)
    existing = await session.scalar(
        select(func.count(Cell.id))
        .where(Cell.location_id == location.id)
        .where(Cell.target_location_id == location.id)
        .where(Cell.target_floor.isnot(None))
    ) or 0
    if existing >= expected_links:
        return

    from core import worldgen as W
    await W.ensure_stairs(session, location)
    await session.commit()


async def is_chest_available(session, cell: Cell) -> bool:
    """Сундук доступен, если он есть на клетке и таймер восстановления вышел."""
    if not cell or not cell.has_chest:
        return False
    if cell.chest_respawn_at and cell.chest_respawn_at > datetime.utcnow():
        return False
    return True


async def mark_visited(session, character: Character, cell: Cell):
    """Record fog-of-war progress for the player's current cell."""
    result = await session.execute(
        select(VisitedCell)
        .where(VisitedCell.character_id == character.id)
        .where(VisitedCell.location_id == cell.location_id)
        .where(VisitedCell.floor == (cell.floor or 0))
        .where(VisitedCell.x == cell.x)
        .where(VisitedCell.y == cell.y)
    )
    if result.scalar_one_or_none() is None:
        session.add(VisitedCell(
            character_id=character.id,
            location_id=cell.location_id,
            floor=cell.floor or 0,
            x=cell.x,
            y=cell.y,
        ))


@router.callback_query(F.data.startswith("move:"))
async def move_direction(callback: CallbackQuery):
    direction = callback.data.split(":")[1]
    direction = DIRECTION_ALIASES.get(direction, direction)
    dx, dy = DIRECTIONS.get(direction, (0, 0))

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
            .where(Cell.floor == (character.floor or 0))
            .where(Cell.x == new_x)
            .where(Cell.y == new_y)
        )
        target = result.scalar_one_or_none()
        if not target or not target.is_passable:
            await callback.answer("Туда нельзя пройти!", show_alert=True)
            return

        # Check seamless / floor transition
        if target.target_location_id is not None and target.target_x is not None and target.target_y is not None:
            dest_floor = target.target_floor if target.target_floor is not None else 0
            result = await session.execute(
                select(Cell)
                .where(Cell.location_id == target.target_location_id)
                .where(Cell.floor == dest_floor)
                .where(Cell.x == target.target_x)
                .where(Cell.y == target.target_y)
            )
            dest_cell = result.scalar_one_or_none()
            if dest_cell:
                # Предупреждение по min_level: вход в локацию выше уровнем
                # разрешён, но игрок видит alert — решение остаётся за ним.
                if target.target_location_id != character.location_id:
                    dest_loc = await session.get(Location, target.target_location_id)
                    if dest_loc and (dest_loc.min_level or 1) > character.level:
                        await callback.answer(
                            f"⚠️ {dest_loc.name} — опасность! Рекомендуется "
                            f"{dest_loc.min_level}+ уровень, у тебя {character.level}. "
                            f"Ты входишь на свой страх и риск…",
                            show_alert=True,
                        )
                dest_loc = await session.get(Location, target.target_location_id)
                character.location_id = target.target_location_id
                character.location = dest_loc
                character.floor = dest_floor
                character.cell_id = dest_cell.id
                character.cell = dest_cell
                await mark_visited(session, character, dest_cell)
                await session.commit()

                # realtime — переход между локациями / этажами
                try:
                    from core.realtime import publish as rt_publish
                    from core.vip import is_vip_active as vip_active
                    await rt_publish("player_move", {
                        "character_id": character.id,
                        "name": character.name,
                        "location_id": character.location_id,
                        "location_name": dest_loc.name if dest_loc else "",
                        "floor": dest_floor,
                        "x": dest_cell.x,
                        "y": dest_cell.y,
                        "from_location_id": current.location_id if current else None,
                        "is_vip": vip_active(character),
                    })
                except Exception:
                    pass
                await show_cell(callback, character, dest_loc, session)
                return

        character.cell_id = target.id
        character.cell = target
        await mark_visited(session, character, target)
        await session.commit()

        # realtime — движение внутри локации
        try:
            from core.realtime import publish as rt_publish
            from core.vip import is_vip_active as vip_active
            await rt_publish("player_move", {
                "character_id": character.id,
                "name": character.name,
                "location_id": character.location_id,
                "location_name": character.location.name if character.location else "",
                "floor": character.floor or 0,
                "x": target.x,
                "y": target.y,
                "is_vip": vip_active(character),
            })
        except Exception:
            pass
        await show_cell(callback, character, character.location, session)


@router.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery):
    await callback.answer("Туда нельзя пройти.", show_alert=True)


@router.callback_query(F.data == "cell_transition")
async def cell_transition(callback: CallbackQuery):
    """Use the transition on the current cell: stairs between floors or a door."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer("Ошибка перехода.", show_alert=True)
            return

        result = await session.execute(
            select(Character)
            .where(Character.user_id == user.id)
            .options(selectinload(Character.location), selectinload(Character.cell))
        )
        character = result.scalar_one_or_none()
        if not character or not character.cell:
            await callback.answer("Ошибка перехода.", show_alert=True)
            return

        current = character.cell
        if (
            current.target_location_id is None
            or current.target_x is None
            or current.target_y is None
        ):
            await callback.answer("Здесь нет перехода.", show_alert=True)
            return

        dest_floor = current.target_floor if current.target_floor is not None else 0
        result = await session.execute(
            select(Cell)
            .where(Cell.location_id == current.target_location_id)
            .where(Cell.floor == dest_floor)
            .where(Cell.x == current.target_x)
            .where(Cell.y == current.target_y)
        )
        dest_cell = result.scalar_one_or_none()
        if not dest_cell or not dest_cell.is_passable:
            await callback.answer("Переход ведёт в непроходимую клетку.", show_alert=True)
            return

        dest_loc = await session.get(Location, current.target_location_id)
        if not dest_loc:
            await callback.answer("Локация перехода не найдена.", show_alert=True)
            return

        old_location_id = character.location_id
        if dest_loc.id != character.location_id and (dest_loc.min_level or 1) > character.level:
            await callback.answer(
                f"⚠️ {dest_loc.name} — опасность! Рекомендуется "
                f"{dest_loc.min_level}+ уровень, у тебя {character.level}. "
                f"Ты входишь на свой страх и риск…",
                show_alert=True,
            )

        character.location_id = dest_loc.id
        character.location = dest_loc
        character.floor = dest_floor
        character.cell_id = dest_cell.id
        character.cell = dest_cell
        await mark_visited(session, character, dest_cell)
        await session.commit()

        try:
            from core.realtime import publish as rt_publish
            from core.vip import is_vip_active as vip_active
            await rt_publish("player_move", {
                "character_id": character.id,
                "name": character.name,
                "location_id": dest_loc.id,
                "location_name": dest_loc.name,
                "floor": dest_floor,
                "x": dest_cell.x,
                "y": dest_cell.y,
                "from_location_id": old_location_id,
                "via": "cell_transition",
                "is_vip": vip_active(character),
            })
        except Exception:
            pass

        await show_cell(callback, character, dest_loc, session)


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
            .options(selectinload(Character.cell))
        )
        character = result.scalar_one_or_none()
        if not character or not character.cell:
            await callback.answer("Ошибка.", show_alert=True)
            return

        cell = character.cell
        # Мобы теперь ходят по карте — смотрим живые спавны на этой клетке
        spawn = await spawn_at_cell(session, cell)
        chest_ready = await is_chest_available(session, cell)

        lines = [f"🔍 <b>Осмотр клетки [{cell.x},{cell.y}]</b>\n"]
        lines.append(f"<i>{cell.name}</i>\n")
        lines.append(f"{cell.description}\n")

        found = []
        if spawn and spawn.mob:
            hp_note = ""
            if spawn.current_hp and spawn.current_hp < spawn.mob.hp:
                hp_note = f" <i>(ранен: {spawn.current_hp}/{spawn.mob.hp} HP)</i>"
            found.append(
                f"👾 Ты заметил врага: <b>{spawn.mob.name}</b> "
                f"(ур. {spawn.mob.level}){hp_note}"
            )
        if cell.has_npc:
            role = {
                "crafter": " — ремесленник",
                "auctioneer": " — скупщик",
                "merchant": " — торговец",
            }.get(cell.npc_type, "")
            found.append(f"💬 Здесь кто-то есть: {cell.npc_name}{role}")
        if chest_ready:
            found.append("📦 Ты нашёл сундук!")

        # Достопримечательность: разовая награда за разведку.
        from core import death as core_death
        from core import landmarks as core_landmarks

        mark = core_landmarks.of(cell)
        has_landmark = False
        if mark and await core_landmarks.is_landmark(session, cell):
            if core_landmarks.visited(character, cell):
                found.append(f"{mark['icon']} {cell.name} — уже осмотрено")
            else:
                found.append(f"{mark['icon']} <b>{cell.name}</b> — здесь что-то есть!")
                has_landmark = True

        # Надгробие: чьё-то золото ждёт хозяина.
        grave = await core_death.at(session, cell.location_id, cell.x, cell.y)
        if grave is not None:
            whose = ("твоя" if grave.character_id == character.id
                     else grave.owner_name or "чужая")
            found.append(f"🪦 Надгробие ({whose}) — {grave.gold} 🪙")

        if found:
            lines.append("\n" + "\n".join(found))
        else:
            lines.append(f"\n<i>{random.choice(EMPTY_INSPECT_LINES)}</i>")

        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=inspect_keyboard(
                has_mob=bool(spawn),
                has_npc=cell.has_npc,
                has_chest=chest_ready,
                is_crafter=cell.npc_type == "crafter",
                is_auctioneer=cell.npc_type == "auctioneer",
                has_landmark=has_landmark,
                has_grave=grave is not None,
            ),
            parse_mode="HTML",
        )


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
            .options(selectinload(Character.location), selectinload(Character.cell))
        )
        character = result.scalar_one_or_none()
        if not character or not character.cell:
            await callback.answer("Ошибка.", show_alert=True)
            return

        location = character.location
        floor = character.floor or 0

        result = await session.execute(
            select(Cell)
            .where(Cell.location_id == location.id)
            .where(Cell.floor == floor)
        )
        cells = result.scalars().all()

        result = await session.execute(
            select(VisitedCell)
            .where(VisitedCell.character_id == character.id)
            .where(VisitedCell.location_id == location.id)
            .where(VisitedCell.floor == floor)
        )
        visited_rows = result.scalars().all()
        visited = {(v.x, v.y) for v in visited_rows}
        # Always show the current cell even if somehow missing
        visited.add((character.cell.x, character.cell.y))

        map_path = get_player_map_path(character.id, location.id, floor)
        render_player_map(
            cells, visited, character.cell.x, character.cell.y,
            location.grid_size, map_path,
        )

        floor_label = f" (этаж {floor})" if location.floors_count and location.floors_count > 1 else ""
        caption = f"🗺 <b>{location.name}</b>{floor_label}\n\nИсследовано клеток: {len(visited)}"

        photo = FSInputFile(map_path)
        msg = callback.message
        try:
            if msg and msg.photo:
                from aiogram.types import InputMediaPhoto
                await msg.edit_media(
                    media=InputMediaPhoto(media=photo, caption=caption, parse_mode="HTML"),
                    reply_markup=map_view_keyboard(),
                )
            else:
                if msg:
                    try:
                        await msg.delete()
                    except Exception:
                        pass
                await callback.message.answer_photo(
                    photo=photo, caption=caption, parse_mode="HTML",
                    reply_markup=map_view_keyboard(),
                )
        except Exception:
            await callback.message.answer_photo(
                photo=FSInputFile(map_path), caption=caption, parse_mode="HTML",
                reply_markup=map_view_keyboard(),
            )


@router.callback_query(F.data == "world_map")
async def world_map(callback: CallbackQuery):
    """Карта мира: посещённые локации, текущая позиция, туман войны."""
    from core.map_renderer import render_world_map, get_world_map_path
    from core.worldgen import WORLD_GRID_SIZE
    from core.enums import LocationType

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        result = await session.execute(
            select(Character)
            .where(Character.user_id == user.id)
            .options(selectinload(Character.location))
        )
        character = result.scalar_one_or_none()
        if not character:
            await callback.answer("Сначала создай героя.", show_alert=True)
            return

        locations = (await session.execute(select(Location))).scalars().all()
        visited_rows = await session.execute(
            select(VisitedCell.location_id)
            .where(VisitedCell.character_id == character.id)
            .distinct()
        )
        visited_ids = {row[0] for row in visited_rows.all()}
        visited_ids.add(character.location_id)  # текущая всегда открыта

        map_path = get_world_map_path(character.id)
        render_world_map(locations, visited_ids, character.location_id,
                         WORLD_GRID_SIZE, map_path)

        total = len(locations)
        caption = (f"🌍 <b>Карта мира</b>\n\n"
                   f"Исследовано локаций: <b>{len(visited_ids)} из {total}</b>\n"
                   f"📍 Ты здесь: <b>{character.location.name}</b>")

        # Быстрый travel — обычные только в safe, VIP в любые посещённые
        from core.vip import is_vip_active
        if is_vip_active(character):
            travel_targets = [
                l for l in locations
                if l.id in visited_ids and l.id != character.location_id
            ]
        else:
            travel_targets = [
                l for l in locations
                if l.location_type == LocationType.SAFE
                and l.id in visited_ids and l.id != character.location_id
            ]
        kb = travel_keyboard(travel_targets)

        photo = FSInputFile(map_path)
        msg = callback.message
        try:
            if msg and msg.photo:
                from aiogram.types import InputMediaPhoto
                await msg.edit_media(
                    media=InputMediaPhoto(media=photo),
                    caption=caption, parse_mode="HTML", reply_markup=kb,
                )
            else:
                if msg:
                    try:
                        await msg.delete()
                    except Exception:
                        pass
                await callback.message.answer_photo(
                    photo=photo, caption=caption, parse_mode="HTML", reply_markup=kb,
                )
        except Exception:
            await callback.message.answer_photo(
                photo=FSInputFile(map_path), caption=caption,
                parse_mode="HTML", reply_markup=kb,
            )


@router.callback_query(F.data.startswith("travel:"))
async def travel_to(callback: CallbackQuery):
    """Быстрое перемещение в посещённую локацию (VIP — в любую, обычные — только safe)."""
    from core.enums import LocationType
    from core import worldops as WO
    from core.vip import is_vip_active

    loc_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        result = await session.execute(
            select(Character).where(Character.user_id == user.id)
        )
        character = result.scalar_one_or_none()
        if not character:
            await callback.answer("Ошибка.", show_alert=True)
            return

        loc = await session.get(Location, loc_id)
        if not loc:
            await callback.answer("Локация не найдена.", show_alert=True)
            return
        # Обычные игроки — только в safe, VIP — в любые посещённые
        if not is_vip_active(character) and loc.location_type != LocationType.SAFE:
            await callback.answer("Путешествовать можно только в безопасные локации. VIP — в любые.",
                                  show_alert=True)
            return
        visited = await session.scalar(
            select(func.count(VisitedCell.id))
            .where(VisitedCell.character_id == character.id)
            .where(VisitedCell.location_id == loc_id)
        )
        if not visited and character.location_id != loc_id:
            await callback.answer("Сначала нужно побывать там — мир не откроет "
                                  "неизведанных дорог.", show_alert=True)
            return

        dest = await WO.spawn_cell_of(session, loc)
        if not dest:
            await callback.answer("В локации нет проходимых клеток.", show_alert=True)
            return

        character.location_id = loc.id
        character.floor = 0
        character.cell_id = dest.id
        await mark_visited(session, character, dest)
        await session.commit()

        # realtime
        try:
            from core.realtime import publish as rt_publish
            await rt_publish("player_move", {
                "character_id": character.id,
                "name": character.name,
                "location_id": loc.id,
                "location_name": loc.name,
                "floor": 0,
                "x": dest.x,
                "y": dest.y,
                "via": "travel",
                "is_vip": is_vip_active(character),
            })
        except Exception:
            pass

        await callback.answer(f"🏠 Ты в локации «{loc.name}».")
        await show_cell(callback, character, loc, session)


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
        if cell.npc_type == "crafter":
            builder.button(text="🔨 Ремесло и заточка", callback_data="craft_menu")
        if cell.npc_type == "auctioneer":
            builder.button(text="⚖️ Аукцион", callback_data="auction_menu")
        builder.button(text="◀️ Назад", callback_data="back_to_cell")
        builder.adjust(1)

        await send_or_edit_photo(
            callback,
            f"💬 <b>{cell.npc_name}</b>\n\n<i>{cell.npc_dialogue}</i>",
            reply_markup=builder.as_markup(),
            image_url=cell.image_url,
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

        cell = character.cell
        if not await is_chest_available(session, cell):
            await callback.answer("Сундук уже пуст. Загляни позже.", show_alert=True)
            return

        import random
        from core.vip import apply_vip_chest_gold, is_vip_active
        tier = max(1, cell.chest_tier or 1)
        base_gold = random.randint(5 * tier, 25 * tier)
        gold = apply_vip_chest_gold(base_gold, character)
        character.gold += gold

        # Уникальный лут: статы предметов катаются в момент открытия
        loot = await give_chest_loot(session, character, cell.location_id, tier)

        # Сундук не исчезает навсегда — восстановится через некоторое время
        # VIP — быстрее восстановление (личный множитель не влияет на глобальный, но показываем)
        cell.chest_respawn_at = datetime.utcnow() + timedelta(
            minutes=random.randint(20, 60)
        )
        await session.commit()

        # realtime — открытие сундука
        try:
            from core.realtime import publish as rt_publish
            await rt_publish("chest_opened", {
                "character_id": character.id,
                "name": character.name,
                "location_id": character.location_id,
                "x": cell.x,
                "y": cell.y,
                "gold": gold,
                "is_vip": is_vip_active(character),
            })
        except Exception:
            pass

        text = f"📦 <b>Сундук открыт!</b>\n\nВнутри ты нашёл {gold}🪙 золота."
        if is_vip_active(character) and gold != base_gold:
            text += f" <i>(+{gold - base_gold} бонус VIP)</i>"
        if loot:
            text += "\n\n" + loot_text(loot)
        else:
            text += "\n\n<i>Больше в нём ничего не оказалось.</i>"

        await callback.message.edit_text(
            text,
            reply_markup=back_to_main_keyboard(),
            parse_mode="HTML",
        )


async def show_cell(callback, character, location, session):
    cell = character.cell
    if not cell:
        await send_or_edit_photo(
            callback,
            location_text(location),
            reply_markup=main_menu_keyboard(has_character=True),
            image_url=location.image_url,
        )
        return

    await _ensure_floor_stairs_present(session, location)

    can_dirs = {}
    dir_labels = {}
    for direction, (dx, dy) in DIRECTIONS.items():
        result = await session.execute(
            select(Cell)
            .where(Cell.location_id == location.id)
            .where(Cell.floor == (character.floor or 0))
            .where(Cell.x == cell.x + dx)
            .where(Cell.y == cell.y + dy)
        )
        n = result.scalar_one_or_none()
        passable = n is not None and n.is_passable
        can_dirs[direction] = passable

        if n is None:
            dir_labels[direction] = "⬛"
        elif not n.is_passable:
            # Камни нужны только как рамка карты. Внутри сетки они забивают
            # навигацию, поэтому закрытая внутренняя клетка остаётся обычной
            # тёмной кнопкой (⬛ из клавиатуры).
            edge = n.x in (0, location.grid_size - 1) or n.y in (0, location.grid_size - 1)
            if edge:
                dir_labels[direction] = "🪨"
        elif n.target_location_id is not None and n.target_x is not None and n.target_y is not None:
            # Дверь/переход на соседнюю локацию или этаж: игрок видит это
            # до нажатия стрелки, а направление всё равно остаётся на кнопке.
            dir_labels[direction] = f"🚪{DIRECTION_ARROWS.get(direction, '')}"

    transition_label, transition_hint = _current_transition(cell, location)
    portal_template_id = await _active_portal_template_id(session, cell)
    text = cell_text(
        cell, location.name, portal_active=bool(portal_template_id),
        floor=character.floor or 0, total_floors=location.floors_count or 1,
        transition_hint=transition_hint,
    )

    # Use custom cell/location image if provided and valid
    custom_img = cell.image_url or location.image_url
    if custom_img and get_photo_input(custom_img):
        await send_or_edit_photo(
            callback,
            text,
            reply_markup=cell_movement_keyboard(can_dirs, portal_template_id, dir_labels, transition_label),
            image_url=custom_img,
        )
        return

    result = await session.execute(
        select(Cell)
        .where(Cell.location_id == location.id)
        .where(Cell.floor == (character.floor or 0))
    )
    cells = result.scalars().all()

    img_path = ensure_cell_image(cell, cells, cell.x, cell.y)
    kb = cell_movement_keyboard(can_dirs, portal_template_id, dir_labels, transition_label)

    await send_or_edit_photo(
        callback,
        text,
        reply_markup=kb,
        image_url=img_path,
    )


async def _active_portal_template_id(session, cell: Cell):
    """Returns cell.dungeon_template_id only if that portal is still open for
    new entries (not expired/closed by admin); lazily tidies up the cell if
    the portal has just expired so the entry button disappears immediately."""
    if not cell.dungeon_template_id:
        return None

    from core.dungeons import is_portal_open, close_portal
    from core.models import DungeonTemplate

    template = await session.get(DungeonTemplate, cell.dungeon_template_id)
    if template and is_portal_open(template):
        return template.id

    # Portal expired/closed but the cell link wasn't cleaned up yet — do it now.
    if template:
        await close_portal(session, template)
        await session.commit()
    return None
