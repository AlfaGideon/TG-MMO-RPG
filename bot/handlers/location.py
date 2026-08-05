from aiogram import Router, F
from aiogram.types import CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from sqlalchemy import or_, select, func, update
from sqlalchemy.orm import selectinload

from datetime import timedelta

from core.database import async_session
from core.loot import give_chest_loot
from core.models import User, Character, Location, Cell, VisitedCell
from core.spawns import spawn_at_cell
from core.vip import is_vip_active
from core.map_renderer import (
    render_cell_image, render_player_map, get_neutral_scene_path,
    get_player_map_path, zoom_radius_for, DEFAULT_ZOOM,
)
from core.neutral_tiles import background_for
from bot.keyboards.inline import (
    cell_movement_keyboard, inspect_keyboard,
    main_menu_keyboard, map_view_keyboard,
    world_map_keyboard,
    travel_keyboard, continue_keyboard,
)
from bot.utils.texts import location_text, cell_text, loot_text, format_floor_label
from bot.utils.photos import (
    send_or_edit_photo, get_photo_input, get_npc_image, has_usable_photo,
)
from bot.utils.edit import safe_edit_text

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
        target_label = format_floor_label(
            target_floor, location.floors_count or 1, location.name
        )
        castle_basement = (
            location.name.startswith("Замок")
            and {current_floor, target_floor} == {0, 1}
        )
        if target_floor == current_floor:
            button = f"🪜 Перейти: {target_label}"
            hint = f"🪜 <b>Переход:</b> ведёт на <b>{target_label}</b>."
        else:
            if current_floor < 0 or target_floor < 0:
                going_up = target_floor > current_floor
            elif castle_basement:
                # В стартовых замках floor=1 — это подвал для подкопов,
                # а не второй надземный этаж.
                going_up = target_floor < current_floor
            else:
                going_up = target_floor > current_floor

            if going_up:
                button = f"🪜⬆️ Подняться: {target_label}"
                hint = f"🪜 <b>Лестница вверх:</b> можно подняться на <b>{target_label}</b>."
            else:
                button = f"🪜⬇️ Спуститься: {target_label}"
                hint = f"🪜 <b>Лестница вниз:</b> можно спуститься на <b>{target_label}</b>."
    else:
        button = "🚪 Перейти через дверь"
        hint = "🚪 <b>Дверь:</b> отсюда можно перейти в другую локацию."
    return button, hint


async def _ensure_floor_stairs_present(session, location: Location):
    """Lazy safety net for broken floor links in existing databases.

    There are two independent kinds of floors:

    * ordinary non-negative floors from ``Location.floors_count`` (tower floors
      and the castle basement used by sabotage tunnels);
    * negative underground floors (-1, -2, ...) generated under corner castles.

    The old underground builder reused the central ordinary-stair cell and
    linked each negative level only downward. As a result a player could fall
    from Замок Рассвета into the depths, lose the surface stair, and never
    climb back. We now verify the exact standard stair cells, not just the
    total number of links (old broken underground links used to fool that
    count).
    """
    from core import worldgen as W

    changed = False
    floors = max(1, location.floors_count or 1)
    if floors >= 2:
        # Check the standard positive stair pair explicitly. Counting all
        # self-links is not enough because negative underground links are also
        # self-links and made broken castles look "healthy".
        cx, cy = W.center_of(location.grid_size)
        dx, dy = (1, 0) if cx + 1 < (location.grid_size or 10) - 1 else (-1, 0)
        expected = []
        for floor in range(floors):
            if floor < floors - 1:
                expected.append((cx, cy, floor, floor + 1))
            if floor > 0:
                expected.append((cx + dx, cy + dy, floor, floor - 1))
        ok = True
        for x, y, floor, target_floor in expected:
            c = await W.cell_at(session, location.id, x, y, floor)
            if not (
                c and c.is_passable and c.target_location_id == location.id
                and c.target_x == x and c.target_y == y
                and c.target_floor == target_floor
            ):
                ok = False
                break
        if not ok:
            changed = await W.ensure_stairs(session, location) or changed

    if await W.underground_floors(session, location):
        changed = await W.ensure_underground_stairs(session, location) or changed

    if changed:
        await session.commit()


async def is_chest_available(session, cell: Cell) -> bool:
    """Сундук доступен, если он есть на клетке и таймер восстановления вышел."""
    from core.dates import aware, utcnow
    if not cell or not cell.has_chest:
        return False
    if cell.chest_respawn_at and aware(cell.chest_respawn_at) > utcnow():
        return False
    return True


async def _map_character(callback: CallbackQuery, session, need_cell: bool = False):
    """Персонаж для экранов карты/пути — с починкой битых привязок.

    «Карта» и «В путь» теперь висят в главном меню, поэтому экран обязан
    переживать героев без локации (создание прервалось) и без клетки
    (мир пересоздавали). Возвращает character или None, если ответ уже
    отправлен (продолжение создания / ошибка).
    """
    result = await session.execute(
        select(User).where(User.telegram_id == callback.from_user.id)
    )
    user = result.scalar_one_or_none()
    if not user:
        await callback.answer("Нажми /start, чтобы начать.", show_alert=True)
        return None
    result = await session.execute(
        select(Character)
        .where(Character.user_id == user.id)
        .options(selectinload(Character.location), selectinload(Character.cell))
    )
    character = result.scalar_one_or_none()
    if not character:
        await callback.answer("Сначала создай героя.", show_alert=True)
        return None

    if character.location is None:
        # Герой без локации: создание прервалось до выбора фракции
        # (локация появляется вместе с ней) или мир пересоздавался и
        # старый location_id больше не существует. Возвращаем на шаг
        # создания или чиним привязку к миру.
        from bot.handlers.start import resume_character_creation
        if await resume_character_creation(callback, session, character):
            return None
        fallback = (await session.execute(
            select(Location).order_by(Location.id)
        )).scalars().first()
        if fallback is None:
            await callback.answer("Мир ещё не создан. Загляни позже.", show_alert=True)
            return None
        character.location_id = fallback.id
        await session.commit()
        result = await session.execute(
            select(Character)
            .where(Character.id == character.id)
            .options(selectinload(Character.location), selectinload(Character.cell))
        )
        character = result.scalar_one()

    if need_cell and character.cell is None:
        # Клетка пропала (мигрaции мира): ставим героя на спавн-клетку
        # его локации, иначе карту локации рисовать негде.
        from core import worldops as WO
        dest = await WO.spawn_cell_of(session, character.location)
        if dest is None:
            await callback.answer("В локации нет проходимых клеток.", show_alert=True)
            return None
        character.cell_id = dest.id
        character.floor = 0
        await mark_visited(session, character, dest)
        await session.commit()
        result = await session.execute(
            select(Character)
            .where(Character.id == character.id)
            .options(selectinload(Character.location), selectinload(Character.cell))
        )
        character = result.scalar_one()
    return character


async def _send_map_photo(callback: CallbackQuery, map_path: str, caption: str, reply_markup):
    """Показать картинку карты: заменить текущее фото или отправить новое.

    Раньше у каждого экрана карты был свой экземпляр этого блока, причём
    в «Карте мира» caption передавался аргументом edit_media, который его
    не принимает, — и сообщение каждый раз пересылалось заново.
    """
    from aiogram.types import InputMediaPhoto
    msg = callback.message
    try:
        if msg and msg.photo:
            await msg.edit_media(
                media=InputMediaPhoto(
                    media=FSInputFile(map_path), caption=caption, parse_mode="HTML"
                ),
                reply_markup=reply_markup,
            )
            return
        if msg:
            try:
                await msg.delete()
            except Exception:
                pass
        await callback.message.answer_photo(
            photo=FSInputFile(map_path), caption=caption,
            parse_mode="HTML", reply_markup=reply_markup,
        )
    except Exception:
        await callback.message.answer_photo(
            photo=FSInputFile(map_path), caption=caption,
            parse_mode="HTML", reply_markup=reply_markup,
        )


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


async def _nearby_landing_cell(session, door_cell: Cell):
    """A safe arrival cell next to an inter-location door/tunnel.

    Dig tunnels used to point A-door directly to B-door and B-door directly
    back to A-door. The player landed on the return trigger and visually
    "jumped" between Замок Рассвета and Замок Глубин. For transitions between
    different locations we prefer to land one step inside the destination; the
    door remains next to the player and can still be used to go back.
    """
    if door_cell is None:
        return None

    # Cardinal cells first (clearer on the navigation pad), diagonals second.
    offsets = [(-1, 0), (1, 0), (0, -1), (0, 1),
               (-1, -1), (-1, 1), (1, -1), (1, 1)]
    fallback = None
    for dx, dy in offsets:
        result = await session.execute(
            select(Cell)
            .where(Cell.location_id == door_cell.location_id)
            .where(Cell.floor == (door_cell.floor or 0))
            .where(Cell.x == door_cell.x + dx)
            .where(Cell.y == door_cell.y + dy)
        )
        c = result.scalar_one_or_none()
        if not c or not c.is_passable:
            continue
        if fallback is None:
            fallback = c
        # Best landing: not another door/stair, so the next click does not
        # immediately trigger a different transition.
        if c.target_location_id is None:
            return c
    return fallback


async def _resolve_transition_destination(session, link_cell: Cell, source_location_id: int):
    """Return destination floor/cell for a transition cell.

    For ordinary stairs and world borders we keep the exact configured target.
    For reciprocal inter-location doors (notably player-dug castle tunnels),
    landing on the configured target means landing on the return door itself.
    In that case we shift the arrival to a neighboring passable cell.
    """
    dest_floor = link_cell.target_floor if link_cell.target_floor is not None else 0
    result = await session.execute(
        select(Cell)
        .where(Cell.location_id == link_cell.target_location_id)
        .where(Cell.floor == dest_floor)
        .where(Cell.x == link_cell.target_x)
        .where(Cell.y == link_cell.target_y)
    )
    dest_cell = result.scalar_one_or_none()
    if not dest_cell:
        return dest_floor, None

    is_inter_location = link_cell.target_location_id != source_location_id
    reciprocal = (
        is_inter_location
        and dest_cell.target_location_id == link_cell.location_id
        and (dest_cell.target_floor if dest_cell.target_floor is not None else 0) == (link_cell.floor or 0)
    )
    if reciprocal:
        landing = await _nearby_landing_cell(session, dest_cell)
        if landing is not None:
            return landing.floor or 0, landing
    return dest_floor, dest_cell


@router.callback_query(F.data.startswith("move:"))
async def move_direction(callback: CallbackQuery, state: FSMContext):
    direction = callback.data.split(":")[1]
    direction = DIRECTION_ALIASES.get(direction, direction)
    dx, dy = DIRECTIONS.get(direction, (0, 0))

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer("Ошибка перемещения.", show_alert=True)
            return

        result = await session.execute(
            select(Character)
            .where(Character.user_id == user.id)
            .options(selectinload(Character.location), selectinload(Character.cell))
        )
        character = result.scalar_one_or_none()
        if not character or not character.cell:
            await callback.answer("Ошибка перемещения.", show_alert=True)
            return

        # Получаем текущий зум из состояния
        fsm_data = await state.get_data()
        zoom = fsm_data.get("map_zoom", DEFAULT_ZOOM)

        if character.location:
            await _ensure_floor_stairs_present(session, character.location)

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
            dest_floor, dest_cell = await _resolve_transition_destination(
                session, target, character.location_id
            )
            if not dest_cell or not dest_cell.is_passable:
                # Цель перехода отсутствует или замурована (битая ссылка
                # в данных) — не пускаем игрока ВНУТРЬ клетки-перехода:
                # иначе он «застревает» на лестнице/двери, которая никуда
                # не ведёт, и кнопка перехода вечно показывает ошибку.
                await callback.answer("Переход ведёт в непроходимую клетку.", show_alert=True)
                return

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
            
            # Задания: продвигаем квесты на исследование
            from core.quests import advance_reach
            await advance_reach(session, character, target.target_location_id)

            from core import merchant
            await merchant.maybe_wander(session)
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
            await show_cell(callback, character, dest_loc, session, zoom=zoom)
            return

        character.cell_id = target.id
        character.cell = target
        await mark_visited(session, character, target)
        from core import merchant
        await merchant.maybe_wander(session)
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
        await show_cell(callback, character, character.location, session, zoom=zoom)


@router.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery):
    await callback.answer("Туда нельзя пройти.", show_alert=True)


@router.callback_query(F.data == "cell_transition")
async def cell_transition(callback: CallbackQuery, state: FSMContext):
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

        # Получаем текущий зум из состояния
        fsm_data = await state.get_data()
        zoom = fsm_data.get("map_zoom", DEFAULT_ZOOM)

        if character.location:
            await _ensure_floor_stairs_present(session, character.location)

        current = character.cell
        if (
            current.target_location_id is None
            or current.target_x is None
            or current.target_y is None
        ):
            await callback.answer("Здесь нет перехода.", show_alert=True)
            return

        dest_floor, dest_cell = await _resolve_transition_destination(
            session, current, character.location_id
        )
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
        
        # Задания: продвигаем квесты на исследование
        from core.quests import advance_reach
        await advance_reach(session, character, current.target_location_id)
        
        from core import merchant
        await merchant.maybe_wander(session)
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

        await show_cell(callback, character, dest_loc, session, zoom=zoom)


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

        lines = [ f"🔍 <b>Осмотр клетки [{cell.x},{cell.y}]</b>\n" ]
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

        # Надгробие: чьё-то золото ждёт хозяина (на этом же этаже).
        grave = await core_death.at(session, cell.location_id, cell.x, cell.y,
                                    floor=cell.floor or 0)
        if grave is not None:
            whose = ("твоя" if grave.character_id == character.id
                     else grave.owner_name or "чужая")
            found.append(f"🪦 Надгробие ({whose}) — {grave.gold} 🟤")

        # Другие игроки на клетке
        result_others = await session.execute(
            select(Character)
            .where(Character.location_id == cell.location_id)
            .where(Character.cell_id == cell.id)
            .where(Character.floor == (cell.floor or 0))
            .where(Character.id != character.id)
            .where(Character.stats_locked == True)
        )
        other_chars = result_others.scalars().all()
        has_others = len(other_chars) > 0
        if has_others:
            import core.factions as core_factions
            names_list = []
            for oc in other_chars:
                f_icon = core_factions.FACTIONS.get(core_factions.allegiance(oc), ("", ""))[0] or "👤"
                names_list.append(f"{f_icon} <b>{oc.name}</b> (ур. {oc.level})")
            found.append("👥 <b>Другие герои здесь:</b>\n" + ", ".join(names_list))

        if found:
            lines.append("\n" + "\n".join(found))
        else:
            lines.append(f"\n<i>{random.choice(EMPTY_INSPECT_LINES)}</i>")

        await safe_edit_text(callback, "\n".join(lines),
            reply_markup=inspect_keyboard(
                has_mob=bool(spawn),
                has_npc=cell.has_npc,
                has_chest=chest_ready,
                is_crafter=cell.npc_type == "crafter",
                is_auctioneer=cell.npc_type == "auctioneer",
                has_landmark=has_landmark,
                has_grave=grave is not None,
                has_players=has_others,
            ),
            parse_mode="HTML",
        )


async def _explored_cells(session, character, location_id: int, floor: int):
    """Клетки локации и множество исследованных — общая выборка для
    экранов карты и перемещения, чтобы обе карты всегда совпадали."""
    result = await session.execute(
        select(Cell)
        .where(Cell.location_id == location_id)
        .where(Cell.floor == floor)
    )
    cells = result.scalars().all()

    result = await session.execute(
        select(VisitedCell)
        .where(VisitedCell.character_id == character.id)
        .where(VisitedCell.location_id == location_id)
        .where(VisitedCell.floor == floor)
    )
    visited = {(v.x, v.y) for v in result.scalars().all()}
    # Текущая клетка видна всегда, даже если запись посещения потерялась.
    if character.cell is not None:
        visited.add((character.cell.x, character.cell.y))
    return cells, visited


@router.callback_query(F.data == "show_map")
async def show_map(callback: CallbackQuery, state: FSMContext):
    fsm_data = await state.get_data()
    zoom = fsm_data.get("map_zoom", DEFAULT_ZOOM)
    await _show_map(callback, zoom)


@router.callback_query(F.data.startswith("map_zoom:"))
async def map_zoom(callback: CallbackQuery, state: FSMContext):
    """Кнопки ➕/➖ на карте: приблизить к герою или показать всю локацию.

    Одинаково работает и в разделе «Карта», и на экране перемещения —
    обе карты рисует один и тот же цветной рендер с туманом войны.
    """
    parts = callback.data.split(":")
    screen = parts[1] if len(parts) > 1 else "map"
    zoom = int(parts[2]) if len(parts) > 2 else DEFAULT_ZOOM
    
    # Сохраняем зум в состоянии, чтобы он не сбрасывался при перемещении
    await state.update_data(map_zoom=zoom)
    
    if screen == "cell":
        async with async_session() as session:
            character = await _map_character(callback, session, need_cell=True)
            if character is None:
                return
            await show_cell(callback, character, character.location, session,
                            zoom=zoom)
        return
    await _show_map(callback, zoom)


async def _show_map(callback: CallbackQuery, zoom: int = DEFAULT_ZOOM):
    """Раздел «Карта»: текущая карта локации.

    Отсюда же открывается мировая карта и экран «В путь» — три экрана
    связаны, но не смешивают обзор и путешествия.
    """
    async with async_session() as session:
        character = await _map_character(callback, session, need_cell=True)
        if character is None:
            return

        location = character.location
        floor = character.floor or 0
        cells, visited = await _explored_cells(
            session, character, location.id, floor)

        map_path = get_player_map_path(character.id, location.id, floor, zoom)
        render_player_map(
            cells, visited, character.cell.x, character.cell.y,
            location.grid_size, map_path,
            zoom_radius=zoom_radius_for(location.grid_size, zoom),
        )

        show_floor = (floor != 0) or (location.floors_count and location.floors_count > 1)
        floor_label = f" ({format_floor_label(floor, location.floors_count or 1, location.name)})" if show_floor else ""
        caption = (
            f"🗺 <b>{location.name}</b>{floor_label}\n\n"
            f"Исследовано клеток: {len(visited)}\n\n"
            f"<i>Это раздел «Карта»: отсюда можно открыть 🌍 карту мира "
            f"или отправиться 🥾 в путь. Масштаб меняется кнопками ➕/➖.</i>"
        )

        await _send_map_photo(callback, map_path, caption, map_view_keyboard(zoom))


@router.callback_query(F.data == "world_map")
async def world_map(callback: CallbackQuery):
    """Карта мира: посещённые локации, текущая позиция, туман войны.

    Это просто карта — никаких переходов между замками: быстрые
    путешествия живут на отдельном экране «В путь».
    """
    from core.map_renderer import render_world_map, get_world_map_path
    from core.worldgen import WORLD_GRID_SIZE

    async with async_session() as session:
        character = await _map_character(callback, session)
        if character is None:
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
        caption = (
            f"🌍 <b>Карта мира</b>\n\n"
            f"Исследовано локаций: <b>{len(visited_ids)} из {total}</b>\n"
            f"📍 Ты здесь: <b>{character.location.name}</b>\n\n"
            f"<i>Отправиться в путь — кнопка 🥾 «В путь» в разделе "
            f"«Карта» или в главном меню.</i>"
        )
        await _send_map_photo(callback, map_path, caption, world_map_keyboard())


@router.callback_query(F.data == "journey")
async def journey(callback: CallbackQuery):
    """Экран «В путь»: мгновенные путешествия между посещёнными локациями.

    Раньше список направлений висел прямо под картой мира, и она
    превращалась из карты в пульт переездов. Теперь карта — только
    обзор, а весь travel живёт здесь.
    """
    from core.map_renderer import render_world_map, get_world_map_path
    from core.worldgen import WORLD_GRID_SIZE
    from core.enums import LocationType

    async with async_session() as session:
        character = await _map_character(callback, session)
        if character is None:
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

        # Быстрый travel — обычные только в safe, VIP в любые посещённые
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

        if travel_targets:
            caption = (
                f"🥾 <b>В путь!</b>\n\n"
                f"📍 Ты здесь: <b>{character.location.name}</b>\n\n"
                f"Мгновенные путешествия доступны между уже посещёнными "
                f"безопасными локациями <i>(VIP — любыми посещёнными)</i>.\n\n"
                f"<b>Выбери направление — и вперёд:</b>"
            )
        else:
            caption = (
                f"🥾 <b>В путь!</b>\n\n"
                f"📍 Ты здесь: <b>{character.location.name}</b>\n\n"
                f"Пока доступных направлений нет. Доберись пешком до других "
                f"безопасных локаций — и они откроются здесь для мгновенных "
                f"путешествий <i>(VIP — любые посещённые)</i>."
            )
        await _send_map_photo(callback, map_path, caption, travel_keyboard(travel_targets))


@router.callback_query(F.data.startswith("travel:"))
async def travel_to(callback: CallbackQuery):
    """Быстрое перемещение в посещённую локацию (VIP — в любую, обычные — только safe)."""
    from core.enums import LocationType
    from core import worldops as WO
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
        from core import merchant
        await merchant.maybe_wander(session)
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
async def back_to_cell(callback: CallbackQuery, state: FSMContext):
    """Возврат туда, где игрок стоял, — основной способ «продолжить путь».

    Если героя или клетки почему-то нет (не создан персонаж, битые данные),
    честно показываем меню, а не оставляем игрока с мёртвой кнопкой.
    """
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        character = None
        if user is not None:
            result = await session.execute(
                select(Character)
                .where(Character.user_id == user.id)
                .options(selectinload(Character.location), selectinload(Character.cell))
            )
            character = result.scalar_one_or_none()
        if character and character.cell:
            fsm_data = await state.get_data()
            zoom = fsm_data.get("map_zoom", DEFAULT_ZOOM)
            await show_cell(callback, character, character.location, session, zoom=zoom)
            return

    from bot.utils.texts import WELCOME_TEXT
    await safe_edit_text(
        callback,
        WELCOME_TEXT,
        reply_markup=main_menu_keyboard(has_character=bool(character)),
        parse_mode="HTML",
    )


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
            .options(selectinload(Character.cell), selectinload(Character.location))
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
            
        # Задания у NPC
        from core.quests import available_quests, active_quests, check_deliver
        avail = await available_quests(session, character, npc_name=cell.npc_name)
        for q in avail:
            builder.button(text=f"📜 Взять: {q.name[:20]}", callback_data=f"q_take:{q.id}")
            
        active = await active_quests(session, character)
        for cq in active:
            if cq.quest.npc_name == cell.npc_name and await check_deliver(session, character, cq):
                builder.button(text=f"✅ Сдать: {cq.quest.name[:20]}", callback_data=f"q_finish:{cq.quest.id}")

        builder.button(text="◀️ Назад", callback_data="back_to_cell")
        builder.adjust(1)

        # Своя картинка клетки из админки всегда важнее. Если в старой БД
        # остался пустой или битый путь, откатываемся к встроенному портрету
        # по имени/замку, а не молча отправляем NPC без изображения.
        image_url = (cell.image_url or "").strip()
        if not has_usable_photo(image_url):
            image_url = get_npc_image(
                cell.npc_name, cell.npc_type,
                character.location.name if character.location else None,
            )

        from core import factions as core_factions
        if core_factions.refuses(character, cell.npc_name, cell.npc_type):
            await callback.answer(
                f"😠 {cell.npc_name} даже не смотрит в твою сторону. "
                f"Твои поступки против {core_factions.FACTIONS[core_factions.npc_faction(cell.npc_name)][1]} "
                f"не остались незамеченными.", show_alert=True
            )
            return

        dialogue = cell.npc_dialogue or "Мне нечего тебе сказать."
        greeting_text = core_factions.greeting(character, cell.npc_name, cell.npc_type)

        await send_or_edit_photo(
            callback,
            f"💬 <b>{cell.npc_name}</b>\n\n<i>{dialogue}</i>{greeting_text}",
            reply_markup=builder.as_markup(),
            image_url=image_url,
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
        from core.dates import utcnow
        # Атомарный захват: сундук — общая клетка мира, и двое игроков (или
        # ретрай клиента) могли прочитать «доступен» одновременно. Кто
        # первым отщёлкнул таймер — того и лут, у остальных rowcount == 0.
        new_respawn = utcnow() + timedelta(minutes=random.randint(20, 60))
        claimed = await session.execute(
            update(Cell)
            .where(Cell.id == cell.id)
            .where(Cell.has_chest == True)  # noqa: E712
            .where(or_(Cell.chest_respawn_at.is_(None),
                       Cell.chest_respawn_at <= utcnow()))
            .values(chest_respawn_at=new_respawn)
        )
        if claimed.rowcount != 1:
            await callback.answer("Сундук уже пуст. Загляни позже.", show_alert=True)
            return
        cell.chest_respawn_at = new_respawn

        from core.vip import apply_vip_chest_gold
        tier = max(1, cell.chest_tier or 1)
        base_gold = random.randint(5 * tier, 25 * tier)
        gold = apply_vip_chest_gold(base_gold, character)
        from engine.currency import add_currency, CONVERSION
        add_currency(character, bronze=gold)

        # Уникальный лут: статы предметов катаются в момент открытия
        loot = await give_chest_loot(session, character, cell.location_id, tier)
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

        def fmt_b(val):
            g_v = val // (CONVERSION * CONVERSION)
            rem = val % (CONVERSION * CONVERSION)
            s_v = rem // CONVERSION
            b_v = rem % CONVERSION
            parts = []
            if g_v > 0: parts.append(f"{g_v}🟡")
            if s_v > 0: parts.append(f"{s_v}⚪")
            if b_v > 0 or not parts: parts.append(f"{b_v}🟤")
            return " ".join(parts)

        text = f"📦 <b>Сундук открыт!</b>\n\nВнутри ты нашёл {fmt_b(gold)}."
        if is_vip_active(character) and gold != base_gold:
            text += f" <i>(+{fmt_b(gold - base_gold)} бонус VIP)</i>"
        if loot:
            text += "\n\n" + loot_text(loot)
        else:
            text += "\n\n<i>Больше в нём ничего не оказалось.</i>"

        # Сундук открыт — игрок продолжает прогулку с той же клетки,
        # а не возвращается в главное меню.
        await safe_edit_text(
            callback,
            text,
            reply_markup=continue_keyboard(),
            parse_mode="HTML",
        )


async def show_cell(callback, character, location, session,
                    zoom: int = DEFAULT_ZOOM):
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
    vip = is_vip_active(character)
    text = cell_text(
        cell, location.name, portal_active=bool(portal_template_id),
        floor=character.floor or 0, total_floors=location.floors_count or 1,
        transition_hint=transition_hint,
    )

    # Бродячий торговец: если он стоит в этой локации, игрок видит его
    # в описании клетки и получает кнопку «🧳 Торговец».
    from core import merchant
    merchant_state = await merchant.load(session)
    has_merchant = bool(merchant_state and
                        int(merchant_state.get("location_id") or 0) == location.id)
    if has_merchant:
        text += ("\n\n🧳 <b>Здесь стоит бродячий торговец!</b> "
                 "<i>«Свежие диковинки — дёшево, только до заката!»</i>")

    is_basement = bool(location.name.startswith("Замок") and character.floor == 1)

    # Своя картинка клетки (например, портрет NPC) всегда важнее автоматики.
    # Фон всей локации оставляем резервом: обычные клетки получают более
    # читаемую нейтральную сцену по своему типу/форме дороги.
    # Для больших локаций (замки 25x25) нейтральные фоны не генерируем.
    custom_img = (cell.image_url or "").strip()
    if custom_img and get_photo_input(custom_img):
        await send_or_edit_photo(
            callback, text,
            reply_markup=cell_movement_keyboard(
                can_dirs, portal_template_id, dir_labels, transition_label,
                is_vip=vip, has_merchant=has_merchant,
                is_castle_basement=is_basement),
            image_url=custom_img,
        )
        return

    is_castle_loc = bool(location.grid_size and location.grid_size > 15)
    cells_list = []
    if not is_castle_loc:
        result_cells = await session.execute(
            select(Cell)
            .where(Cell.location_id == location.id)
            .where(Cell.floor == (character.floor or 0))
        )
        cells_list = result_cells.scalars().all()
        neutral = background_for(cell, cells_list)
        if neutral:
            background_url, rotation = neutral
            scene_path = get_neutral_scene_path(
                character.id, location.id, character.floor or 0, cell.id)
            render_cell_image(
                cell, cells_list, cell.x, cell.y, scene_path,
                background_url=background_url, background_rotation=rotation,
            )
            await send_or_edit_photo(
                callback, text,
                reply_markup=cell_movement_keyboard(
                    can_dirs, portal_template_id, dir_labels, transition_label,
                    is_vip=vip, has_merchant=has_merchant,
                    is_castle_basement=is_basement),
                image_url=scene_path,
            )
            return

    # Редкие типы без нейтрального арта используют заданный фон локации;
    # иначе остаётся знакомая карта с туманом войны и масштабом.
    if location.image_url and get_photo_input(location.image_url):
        await send_or_edit_photo(
            callback, text,
            reply_markup=cell_movement_keyboard(
                can_dirs, portal_template_id, dir_labels, transition_label,
                is_vip=vip, has_merchant=has_merchant,
                is_castle_basement=is_basement),
            image_url=location.image_url,
        )
        return

    img_path = get_player_map_path(character.id, location.id,
                                   character.floor or 0, zoom)
    cells, visited = await _explored_cells(
        session, character, location.id, character.floor or 0)
    render_player_map(
        cells, visited, cell.x, cell.y, location.grid_size, img_path,
        zoom_radius=zoom_radius_for(location.grid_size, zoom),
    )
    kb = cell_movement_keyboard(can_dirs, portal_template_id, dir_labels,
                                transition_label, is_vip=vip,
                                has_merchant=has_merchant,
                                is_castle_basement=is_basement, zoom=zoom)
    await send_or_edit_photo(callback, text, reply_markup=kb, image_url=img_path)


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


@router.callback_query(F.data == "dig_tunnel")
async def dig_tunnel_menu(callback: CallbackQuery):
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
            await callback.answer("Ошибка: персонаж не найден.", show_alert=True)
            return

        loc = character.location
        if not loc.name.startswith("Замок") or character.floor != 1:
            await callback.answer("Эта функция доступна только в подвалах стартовых замков.", show_alert=True)
            return

        # Neighbors config (enmity by circle)
        neighbors = {
            "Замок Рассвета": [("Замок Теней", "cult"), ("Замок Глубин", "scavengers")],
            "Замок Теней": [("Замок Рассвета", "order"), ("Замок Пепла", "guard")],
            "Замок Пепла": [("Замок Теней", "cult"), ("Замок Глубин", "scavengers")],
            "Замок Глубин": [("Замок Рассвета", "order"), ("Замок Пепла", "guard")],
        }

        targets = neighbors.get(loc.name, [])
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()

        lines = [
            "⛏️ <b>Подземные подкопы и диверсии</b>\n\n"
            "Здесь, в глубоких подвалах замка, ты можешь прокопать секретные подземные ходы "
            "к замкам соседних враждебных фракций, чтобы устраивать неожиданные рейды и диверсии!\n\n"
            "Копать можно к двум соседним замкам (по кругу вражды). Диагональный союзник неприкосновен.\n\n"
            "<b>Стоимость прокопки:</b>\n"
            "• 🧱 Железный лом ×10\n"
            "• 🧱 Стальной слиток ×5\n"
            "• 🟤 500 бронзы (авторазмен)\n\n"
            "<b>Доступные направления:</b>\n"
        ]

        for target_name, faction_key in targets:
            target_loc_res = await session.execute(
                select(Location).where(Location.name == target_name)
            )
            target_loc = target_loc_res.scalar_one_or_none()
            is_dug = False
            if target_loc:
                link_exists = await session.scalar(
                    select(Cell)
                    .where(Cell.location_id == loc.id)
                    .where(Cell.floor == 1)
                    .where(Cell.target_location_id == target_loc.id)
                )
                is_dug = link_exists is not None

            if is_dug:
                lines.append(f"✅ Подкоп к <b>{target_name}</b> — <b>ПРОКОПАН</b> (ищи клетку 🚪 на этаже)")
            else:
                lines.append(f"❌ Подкоп к <b>{target_name}</b> — закрыт")
                if target_loc:
                    builder.button(text=f"⛏️ Копать к {target_name}", callback_data=f"dig_to:{character.id}:{target_loc.id}")

        builder.button(text="◀️ Назад", callback_data="back_to_cell")
        builder.adjust(1)

        await safe_edit_text(
            callback,
            "\n".join(lines),
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("dig_to:"))
async def dig_to_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    char_id, target_loc_id = int(parts[1]), int(parts[2])

    async with async_session() as session:
        character = await session.get(Character, char_id)
        if character is None:
            await callback.answer("Персонаж не найден.", show_alert=True)
            return

        target_loc = await session.get(Location, target_loc_id)
        if not target_loc:
            await callback.answer("Цель не найдена.", show_alert=True)
            return

        loc = character.location

        from core.crafting import _count_material, _consume_material
        from engine.currency import total_in_bronze, deduct_currency

        iron_have = await _count_material(session, character.id, 0)
        steel_have = await _count_material(session, character.id, 3)
        gold_have = total_in_bronze(character)

        if iron_have < 10 or steel_have < 5 or gold_have < 500:
            await callback.answer(
                f"Недостаточно ресурсов!\n"
                f"Требуется:\n"
                f"• Железный лом: {iron_have}/10\n"
                f"• Стальной слиток: {steel_have}/5\n"
                f"• Бронза: {gold_have}/500",
                show_alert=True
            )
            return

        link_exists = await session.scalar(
            select(Cell)
            .where(Cell.location_id == loc.id)
            .where(Cell.floor == 1)
            .where(Cell.target_location_id == target_loc.id)
        )
        if link_exists:
            await callback.answer("Этот подкоп уже прокопан!", show_alert=True)
            return

        loc_cells_res = await session.execute(
            select(Cell)
            .where(Cell.location_id == loc.id)
            .where(Cell.floor == 1)
            .where(Cell.is_passable == True)
            .where(Cell.target_location_id.is_(None))
        )
        loc_cells = loc_cells_res.scalars().all()

        target_cells_res = await session.execute(
            select(Cell)
            .where(Cell.location_id == target_loc.id)
            .where(Cell.floor == 1)
            .where(Cell.is_passable == True)
            .where(Cell.target_location_id.is_(None))
        )
        target_cells = target_cells_res.scalars().all()

        if not loc_cells or not target_cells:
            await callback.answer("Ошибка: нет подходящих свободных клеток для подкопа.", show_alert=True)
            return

        import random
        cell_a = random.choice(loc_cells)
        cell_b = random.choice(target_cells)
        landing_a = await _nearby_landing_cell(session, cell_a) or cell_a
        landing_b = await _nearby_landing_cell(session, cell_b) or cell_b

        await _consume_material(session, character.id, 0, 10)
        await _consume_material(session, character.id, 3, 5)
        deduct_currency(character, 500)

        cell_a.target_location_id = target_loc.id
        cell_a.target_x, cell_a.target_y, cell_a.target_floor = landing_b.x, landing_b.y, 1
        cell_a.name = f"Подкоп в {target_loc.name}"
        cell_a.description = f"Секретный подземный ход, прорытый твоими диверсантами к соседям."

        cell_b.target_location_id = loc.id
        cell_b.target_x, cell_b.target_y, cell_b.target_floor = landing_a.x, landing_a.y, 1
        cell_b.name = f"Подкоп из {loc.name}"
        cell_b.description = f"Секретный подземный ход диверсантов из враждебного замка."

        # Award reputation
        import core.factions as core_factions
        core_factions.award(character, "grave_looted")

        await session.commit()

    await callback.answer("Подкоп успешно прокопан! Проход открыт!", show_alert=True)
    await dig_tunnel_menu(callback)
