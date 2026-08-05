import random
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from core import statpoints
from core.database import async_session
from core.enums import ItemSource
from core.loot import roll_drops, grant_item
from core.models import User, Character, DungeonRun, DungeonCell, DungeonTemplate, Cell
from core.stats import attack_power, combat_stats, damage_reduction
from bot.keyboards.inline import (
    dungeon_menu_keyboard, dungeon_movement_keyboard, dungeon_combat_keyboard,
    dungeon_map_keyboard, back_to_main_keyboard, main_menu_keyboard,
)
from core.map_renderer import render_dungeon_map, get_dungeon_map_path
from bot.utils.texts import loot_text
from bot.utils.edit import safe_edit_text

router = Router()

dungeon_combat_state = {}


async def _dungeon_loot(session, character, run_template_id=None, is_chest=False):
    """Лут в подземелье: таблица шаблона данжа, иначе общий пул сундуков."""
    drops = []
    if run_template_id:
        drops = await roll_drops(session, "dungeon", run_template_id, luck=character.luck)
    if not drops:
        drops = await roll_drops(session, "chest", None, luck=character.luck)

    granted = []
    for item, qty, variance in drops:
        granted += await grant_item(
            session, character, item, qty,
            source=ItemSource.DUNGEON.value,
            source_detail="Подземелье",
            # В данже статы гуляют сильнее — оттуда приходят самые интересные вещи
            extra_variance=variance + (0.05 if not is_chest else 0.08),
        )
    return granted

DUNGEON_NAMES = [
    ("Тёмный коридор", "Влажные стены сияют слизью...", "cave"),
    ("Зал костей", "Пол устлан черепами...", "wall"),
    ("Расщелина", "Узкий проход, едва позволяющий пройти...", "cave"),
    ("Подземный ручей", "Вода здесь чёрная и холодная...", "water"),
    ("Старый склад", "Полки пусты, но пахнет порохом...", "road"),
    ("Алтарь теней", "Каменный столб с древними рунами...", "wall"),
    ("Грибной туннель", "Гигантские грибы светятся тусклым голубым...", "cave"),
    ("Обвал", "Завал из камней перекрывает половину прохода...", "wall"),
    ("Тюремная камера", "Ржавые кандалы висят на стене...", "cave"),
    ("Кристальная пещера", "Стены усыпаны тёмными кристаллами...", "cave"),
]

DEFAULT_MOB_NAMES = ["Пещерный паук", "Теневой крыс", "Скелет-страж", "Болотный слизень", "Древний призрак"]

DIRECTIONS = {
    "n": (-1, 0), "s": (1, 0), "w": (0, -1), "e": (0, 1),
    "nw": (-1, -1), "ne": (-1, 1), "sw": (1, -1), "se": (1, 1),
}
DIRECTION_ALIASES = {
    "north": "n", "south": "s", "west": "w", "east": "e",
}


def _dungeon_config(template: "DungeonTemplate | None"):
    """Returns generation parameters, falling back to sane defaults when no
    admin-configured template is attached to the entrance cell."""
    if template is None:
        return {
            "size": 25,
            "wall_chance": 0.22,
            "chest_chance": 0.06,
            "mob_chance": 0.18,
            "mob_level_min": 1,
            "mob_level_max": 5,
            "mob_names": DEFAULT_MOB_NAMES,
        }
    mob_names = [n.strip() for n in (template.mob_pool or "").split(",") if n.strip()] or DEFAULT_MOB_NAMES
    return {
        "size": max(5, template.grid_size),
        "wall_chance": template.wall_chance,
        "chest_chance": template.chest_chance,
        "mob_chance": template.mob_chance,
        "mob_level_min": template.mob_level_min,
        "mob_level_max": template.mob_level_max,
        "mob_names": mob_names,
    }


def _spawn_xy(template):
    cfg = _dungeon_config(template)
    center = cfg["size"] // 2
    return center, center


def _generate_dungeon(run_id: int, seed: int, floor: int, template=None):
    random.seed(seed + floor * 1000 + run_id)
    cfg = _dungeon_config(template)
    size = cfg["size"]
    spawn_x, spawn_y = _spawn_xy(template)
    cells = []
    for x in range(size):
        for y in range(size):
            is_wall = random.random() < cfg["wall_chance"] and (x, y) != (spawn_x, spawn_y)
            name, desc, tile = random.choice(DUNGEON_NAMES)
            cell = DungeonCell(
                run_id=run_id,
                x=x, y=y,
                name=name,
                description=desc,
                is_passable=not is_wall,
                tile_type=tile if not is_wall else "wall",
                has_mob=(not is_wall and random.random() < cfg["mob_chance"] and (x, y) != (spawn_x, spawn_y)),
                mob_name=random.choice(cfg["mob_names"]),
                mob_level=random.randint(cfg["mob_level_min"], max(cfg["mob_level_min"], cfg["mob_level_max"])) + (floor - 1),
                mob_hp=random.randint(20, 50) + floor * 10,
                mob_damage=random.randint(3, 8) + floor * 2,
                mob_defense=random.randint(1, 4) + floor,
                mob_gold=random.randint(5, 20) + floor * 5,
                mob_exp=random.randint(10, 30) + floor * 10,
                has_chest=(not is_wall and random.random() < cfg["chest_chance"]),
                chest_gold=random.randint(10, 40) + floor * 10,
                has_exit=(x == 0 and y == 0),
            )
            cells.append(cell)
    return cells


async def _get_template(session, run: DungeonRun):
    if run.template_id:
        return await session.get(DungeonTemplate, run.template_id)
    return None


async def _current_cell(session, run: DungeonRun) -> DungeonCell:
    """Returns the dungeon cell the character currently stands on (last visited,
    or the template's spawn point on a fresh run)."""
    result = await session.execute(
        select(DungeonCell)
        .where(DungeonCell.run_id == run.id)
        .where(DungeonCell.is_visited == True)
        .order_by(DungeonCell.id.desc())
        .limit(1)
    )
    current = result.scalar_one_or_none()
    if current:
        return current

    template = await _get_template(session, run)
    spawn_x, spawn_y = _spawn_xy(template)
    result = await session.execute(
        select(DungeonCell)
        .where(DungeonCell.run_id == run.id)
        .where(DungeonCell.x == spawn_x)
        .where(DungeonCell.y == spawn_y)
    )
    current = result.scalar_one()
    current.is_visited = True
    return current


async def _get_can_dirs(session, run: DungeonRun, current: DungeonCell):
    can_dirs = {}
    for direction, (dx, dy) in DIRECTIONS.items():
        result = await session.execute(
            select(DungeonCell)
            .where(DungeonCell.run_id == run.id)
            .where(DungeonCell.x == current.x + dx)
            .where(DungeonCell.y == current.y + dy)
        )
        n = result.scalar_one_or_none()
        can_dirs[direction] = n is not None and n.is_passable
    return can_dirs


@router.callback_query(F.data == "dungeon_menu")
async def dungeon_menu(callback: CallbackQuery):
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
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        result = await session.execute(
            select(DungeonRun)
            .where(DungeonRun.character_id == character.id)
            .where(DungeonRun.is_active == True)
        )
        run = result.scalar_one_or_none()

        # Меню подземелья «в кармане» — VIP-удобство. Обычный герой
        # попадает внутрь только через портал на клетке, поэтому кнопки
        # у него нет; прямой колбэк тоже закрываем, чтобы старое
        # сообщение с кнопкой не осталось лазейкой.
        from core.vip import is_vip_active
        if run is None and not is_vip_active(character):
            await callback.answer(
                "🗿 Подземелье открывается только у портала на карте. "
                "Носить вход с собой могут лишь VIP.",
                show_alert=True,
            )
            return

        if run:
            current = await _current_cell(session, run)
            can_dirs = await _get_can_dirs(session, run, current)
            await session.commit()
            await safe_edit_text(
                callback,
                f"🗿 <b>Подземелье</b>\n\nТы уже внутри! Этаж {run.floor}.\nВыбери действие:",
                reply_markup=dungeon_movement_keyboard(can_dirs),
                parse_mode="HTML",
            )
        else:
            await safe_edit_text(callback, "🗿 <b>Подземелье Проклятых</b>\n\n"
                "Здесь каждый заход уникален. Процедурная генерация создаёт новые лабиринты для каждого игрока.\n"
                "Вход в подземелье — это портал на карте мира (клетка с порталом). "
                "Дойди до него и нажми «🕳 Войти в подземелье», когда окажешься на этой клетке.\n\n"
                "⚠️ Проходить можно только в одиночку!",
                reply_markup=dungeon_menu_keyboard(),
                parse_mode="HTML",
            )


@router.callback_query(F.data == "dungeon_info")
async def dungeon_info(callback: CallbackQuery):
    await safe_edit_text(callback, "📜 <b>Правила подземелья</b>\n\n"
        "• Подземелья появляются как порталы на карте мира — их создаёт администратор\n"
        "• Когда портал открывается, все игроки получают уведомление с точным местоположением\n"
        "• Дойди до клетки с порталом и нажми «🕳 Войти в подземелье»\n"
        "• Каждый заход генерирует уникальное подземелье (не связано с картой мира)\n"
        "• Размер, число этажей и сложность зависят от шаблона портала\n"
        "• Монстры и сундуки случайны\n"
        "• Выход в левом верхнем углу [0,0]\n"
        "• Проходить можно только в одиночку\n"
        "• При выходе прогресс сохраняется до следующего захода\n\n"
        "<i>Удачи, искатель...</i>",
        reply_markup=back_to_main_keyboard(),
        parse_mode="HTML",
    )


async def _enter_dungeon(callback: CallbackQuery, template_id: int):
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
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        result = await session.execute(
            select(DungeonRun)
            .where(DungeonRun.character_id == character.id)
            .where(DungeonRun.is_active == True)
        )
        existing = result.scalar_one_or_none()
        if existing:
            await show_dungeon_cell(callback, existing, session)
            return

        template = await session.get(DungeonTemplate, template_id)
        if not template:
            await callback.answer("Портал уже закрылся.", show_alert=True)
            return

        from core.dungeons import is_portal_open
        if not is_portal_open(template):
            await callback.answer("Портал уже закрылся для новых искателей.", show_alert=True)
            return

        seed = random.randint(1, 1000000)
        run = DungeonRun(
            character_id=character.id,
            template_id=template.id,
            seed=seed,
            floor=1,
            is_active=True,
        )
        session.add(run)
        await session.flush()

        cells = _generate_dungeon(run.id, seed, 1, template)
        for cell in cells:
            session.add(cell)
        await session.commit()

        await show_dungeon_cell(callback, run, session)


@router.callback_query(F.data.startswith("dungeon_enter_tpl:"))
async def dungeon_enter_with_template(callback: CallbackQuery):
    template_id = int(callback.data.split(":")[1])
    await _enter_dungeon(callback, template_id=template_id)


@router.callback_query(F.data == "dungeon_exit")
async def dungeon_exit(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        result = await session.execute(
            select(Character).where(Character.user_id == user.id)
        )
        character = result.scalar_one_or_none()
        if character:
            result = await session.execute(
                select(DungeonRun)
                .where(DungeonRun.character_id == character.id)
                .where(DungeonRun.is_active == True)
            )
            run = result.scalar_one_or_none()
            if run:
                run.is_active = False
                run.completed_at = datetime.utcnow()
                await session.commit()

    await safe_edit_text(callback, "🏃 <b>Ты покинул подземелье.</b>\n\nСледующий заход создаст новое проклятое логово...",
        reply_markup=main_menu_keyboard(has_character=True),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("dungeon_move:"))
async def dungeon_move(callback: CallbackQuery):
    direction = callback.data.split(":")[1]
    direction = DIRECTION_ALIASES.get(direction, direction)
    dx, dy = DIRECTIONS.get(direction, (0, 0))

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

        result = await session.execute(
            select(DungeonRun)
            .where(DungeonRun.character_id == character.id)
            .where(DungeonRun.is_active == True)
        )
        run = result.scalar_one_or_none()
        if not run:
            await callback.answer("Ты не в подземелье.", show_alert=True)
            return

        current = await _current_cell(session, run)

        new_x, new_y = current.x + dx, current.y + dy
        result = await session.execute(
            select(DungeonCell)
            .where(DungeonCell.run_id == run.id)
            .where(DungeonCell.x == new_x)
            .where(DungeonCell.y == new_y)
        )
        target = result.scalar_one_or_none()
        if not target or not target.is_passable:
            await callback.answer("Туда нельзя пройти!", show_alert=True)
            return

        target.is_visited = True
        await session.commit()

        if target.has_exit:
            run.floor += 1
            result = await session.execute(
                select(DungeonCell).where(DungeonCell.run_id == run.id)
            )
            old_cells = result.scalars().all()
            for c in old_cells:
                await session.delete(c)
            await session.flush()

            template = await _get_template(session, run)
            cells = _generate_dungeon(run.id, run.seed, run.floor, template)
            for cell in cells:
                session.add(cell)
            await session.commit()

            await callback.answer(f"Ты спустился на этаж {run.floor}!", show_alert=True)
            await show_dungeon_cell(callback, run, session)
            return

        await show_dungeon_cell(callback, run, session)


@router.callback_query(F.data == "dungeon_inspect")
async def dungeon_inspect(callback: CallbackQuery):
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

        result = await session.execute(
            select(DungeonRun)
            .where(DungeonRun.character_id == character.id)
            .where(DungeonRun.is_active == True)
        )
        run = result.scalar_one_or_none()
        if not run:
            await callback.answer("Ты не в подземелье.", show_alert=True)
            return

        current = await _current_cell(session, run)
        await session.commit()

        lines = [f"🔍 <b>Осмотр [{current.x},{current.y}]</b>\n"]
        lines.append(f"<i>{current.name}</i>\n")
        lines.append(f"{current.description}\n")

        found = []
        if current.has_mob:
            found.append(f"👾 {current.mob_name} (ур. {current.mob_level})")
        if current.has_chest:
            found.append("📦 Сундук!")
        if current.has_exit:
            found.append("🚪 Лестница вниз!")

        if found:
            lines.append("\n" + "\n".join(found))
        else:
            lines.append(f"\n<i>{random.choice(['Тишина...', 'Ничего необычного.', 'Пусто.', 'Только эхо отвечает тебе.'])}</i>")

        builder = InlineKeyboardBuilder()
        if current.has_mob:
            builder.button(text="⚔️ Атаковать", callback_data="dungeon_attack")
        if current.has_chest:
            builder.button(text="📦 Открыть", callback_data="dungeon_open_chest")
        builder.button(text="◀️ Назад", callback_data="dungeon_back")
        builder.adjust(1)

        await safe_edit_text(callback, "\n".join(lines),
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "dungeon_attack")
async def dungeon_attack(callback: CallbackQuery):
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

        result = await session.execute(
            select(DungeonRun)
            .where(DungeonRun.character_id == character.id)
            .where(DungeonRun.is_active == True)
        )
        run = result.scalar_one_or_none()
        if not run:
            await callback.answer("Ты не в подземелье.", show_alert=True)
            return

        current = await _current_cell(session, run)
        await session.commit()

        if not current.has_mob:
            await callback.answer("Здесь нет врагов.", show_alert=True)
            return

        dungeon_combat_state[callback.from_user.id] = {
            "cell_id": current.id,
            "mob_hp": current.mob_hp,
            "mob_name": current.mob_name,
            "mob_damage": current.mob_damage,
            "mob_defense": current.mob_defense,
            "mob_gold": current.mob_gold,
            "mob_exp": current.mob_exp,
            "char_hp": character.current_hp,
            "rounds": 0,
            "template_id": run.template_id,
        }

        await safe_edit_text(
            callback,
            f"⚔️ <b>Бой с {current.mob_name}</b>\n\n"
            f"Ур. {current.mob_level} | HP: {current.mob_hp}\n"
            f"Твой HP: {character.current_hp}/{character.max_hp}",
            reply_markup=dungeon_combat_keyboard(),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "dungeon_flee")
async def dungeon_flee(callback: CallbackQuery):
    dungeon_combat_state.pop(callback.from_user.id, None)
    await safe_edit_text(callback, "🏃 Ты отступил. Монстр не стал преследовать...",
        reply_markup=back_to_main_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "dungeon_combat_attack")
async def dungeon_combat_attack(callback: CallbackQuery):
    state = dungeon_combat_state.get(callback.from_user.id)
    if not state:
        await callback.answer("Бой не найден.", show_alert=True)
        return

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        result = await session.execute(
            select(Character).where(Character.user_id == user.id)
        )
        character = result.scalar_one_or_none()

        # Урон считается с учётом надетых уникальных предметов
        stats = await combat_stats(session, character)
        char_dmg = max(1, attack_power(stats, character) + random.randint(-2, 4))
        mob_dmg = max(0, state["mob_damage"] - damage_reduction(stats) + random.randint(-1, 2))

        state["mob_hp"] -= char_dmg
        state["char_hp"] -= mob_dmg
        state["rounds"] += 1

        if state["mob_hp"] <= 0:
            from engine.currency import add_currency
            add_currency(character, bronze=state["mob_gold"])
            character.experience += state["mob_exp"]
            character.current_hp = max(1, state["char_hp"])

            # Уровень даёт очки характеристик (вкладываются вручную в
            # профиле), а не фиксированный прирост класса — см. battle.py.
            leveled = 0
            points_gained = 0
            needed = character.level * 100
            while character.experience >= needed:
                character.experience -= needed
                character.level += 1
                leveled += 1
                points_gained += statpoints.perks_for_level(character.level)
                needed = character.level * 100
            if leveled:
                character.stat_points = (character.stat_points or 0) + points_gained
                character.current_hp = character.max_hp
                character.current_mp = character.max_mp

            result = await session.execute(
                select(DungeonCell).where(DungeonCell.id == state["cell_id"])
            )
            cell = result.scalar_one_or_none()
            if cell:
                cell.has_mob = False

            loot = await _dungeon_loot(session, character, run_template_id=state.get("template_id"))

            await session.commit()
            del dungeon_combat_state[callback.from_user.id]

            text = (
                f"🎉 <b>Победа в подземелье!</b>\n\n"
                f"Ты поверг {state['mob_name']}!\n"
                f"💰 +{state['mob_gold']}🟤 | ⭐ +{state['mob_exp']} опыта"
            )
            if leveled:
                text += (f"\n\n🎖 <b>Новый уровень: {character.level}!</b>\n"
                         f"🎯 Получено очков характеристик: <b>+{points_gained}</b>.\n"
                         f"<i>Распредели их: 🧙 Профиль → 🎯 Очки характеристик.</i>")
            if loot:
                text += "\n\n" + loot_text(loot)

            await safe_edit_text(
                callback,
                text,
                reply_markup=main_menu_keyboard(has_character=True),
                parse_mode="HTML",
            )
            return

        if state["char_hp"] <= 0:
            character.current_hp = 1
            # Паритет с боем на поверхности и с браузерным стеком: смерть
            # в подземелье — это рана и надгробие с частью добра, а не
            # просто «едва унёс ноги» без последствий.
            from bot.handlers.battle import _lose_bag
            note = await _lose_bag(session, character)
            await session.commit()
            del dungeon_combat_state[callback.from_user.id]

            await safe_edit_text(callback, "💀 <b>Поражение в подземелье...</b>\n\n"
                "Ты едва унёс ноги, оставив кровавый след." + note,
                reply_markup=main_menu_keyboard(has_character=True),
                parse_mode="HTML",
            )
            return

        await session.commit()

        await safe_edit_text(
            callback,
            f"⚔️ <b>Раунд {state['rounds']}</b>\n\n"
            f"Ты нанёс {char_dmg} урона!\n"
            f"{state['mob_name']} отвечает {mob_dmg} урона!\n\n"
            f"❤️ Ты: {state['char_hp']}/{character.max_hp}\n"
            f"👾 {state['mob_name']}: {state['mob_hp']}",
            reply_markup=dungeon_combat_keyboard(),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "dungeon_open_chest")
async def dungeon_open_chest(callback: CallbackQuery):
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

        result = await session.execute(
            select(DungeonRun)
            .where(DungeonRun.character_id == character.id)
            .where(DungeonRun.is_active == True)
        )
        run = result.scalar_one_or_none()
        if not run:
            await callback.answer("Ты не в подземелье.", show_alert=True)
            return

        current = await _current_cell(session, run)

        if not current.has_chest:
            await callback.answer("Здесь нет сундука.", show_alert=True)
            return

        from engine.currency import add_currency, CONVERSION
        add_currency(character, bronze=current.chest_gold)
        current.has_chest = False

        # Уникальный лут: сначала таблица подземелья, потом общий пул сундуков
        loot = await _dungeon_loot(session, character, run.template_id, is_chest=True)
        await session.commit()

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

        text = f"📦 <b>Сундук открыт!</b>\n\nВнутри {fmt_b(current.chest_gold)}."
        if loot:
            text += "\n\n" + loot_text(loot)

        await safe_edit_text(
            callback,
            text,
            reply_markup=back_to_main_keyboard(),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "dungeon_map")
async def dungeon_map(callback: CallbackQuery):
    """Карта подземелья: открытые клетки, сундуки, монстры и лестница."""
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

        result = await session.execute(
            select(DungeonRun)
            .where(DungeonRun.character_id == character.id)
            .where(DungeonRun.is_active == True)
        )
        run = result.scalar_one_or_none()
        if not run:
            await callback.answer("Ты не в подземелье.", show_alert=True)
            return

        current = await _current_cell(session, run)
        await session.commit()

        result = await session.execute(
            select(DungeonCell).where(DungeonCell.run_id == run.id)
        )
        cells = result.scalars().all()

        template = await _get_template(session, run)
        size = _dungeon_config(template)["size"]
        seen = sum(1 for c in cells if c.is_visited)

        path = get_dungeon_map_path(run.id, run.floor)
        render_dungeon_map(cells, current.x, current.y, size, path)

    caption = (
        f"🗺 <b>Карта подземелья — этаж {run.floor}</b>\n"
        f"📍 Ты на [{current.x},{current.y}] · изучено клеток: {seen}\n\n"
        "🟣 лестница вниз · 🟡 сундук · 🔴 монстр · ⬛ стена\n"
        "<i>Тёмное — ещё не исследовано.</i>"
    )

    photo = FSInputFile(path)
    msg = callback.message
    try:
        if msg and msg.photo:
            from aiogram.types import InputMediaPhoto
            await msg.edit_media(
                media=InputMediaPhoto(media=photo, caption=caption, parse_mode="HTML"),
                reply_markup=dungeon_map_keyboard(),
            )
        else:
            if msg:
                try:
                    await msg.delete()
                except Exception:
                    pass
            await callback.message.answer_photo(
                photo=photo, caption=caption, parse_mode="HTML",
                reply_markup=dungeon_map_keyboard(),
            )
    except Exception:
        await callback.message.answer_photo(
            photo=FSInputFile(path), caption=caption, parse_mode="HTML",
            reply_markup=dungeon_map_keyboard(),
        )


@router.callback_query(F.data == "dungeon_back")
async def dungeon_back(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        result = await session.execute(
            select(Character).where(Character.user_id == user.id)
        )
        character = result.scalar_one_or_none()
        if character:
            result = await session.execute(
                select(DungeonRun)
                .where(DungeonRun.character_id == character.id)
                .where(DungeonRun.is_active == True)
            )
            run = result.scalar_one_or_none()
            if run:
                await show_dungeon_cell(callback, run, session)
                return
    await safe_edit_text(
        callback,
        "🗿 Подземелье",
        reply_markup=dungeon_menu_keyboard(),
        parse_mode="HTML",
    )


async def show_dungeon_cell(callback, run, session):
    current = await _current_cell(session, run)
    await session.commit()

    can_dirs = await _get_can_dirs(session, run, current)
    text = (
        f"🗿 <b>Подземелье Проклятых — Этаж {run.floor}</b>\n"
        f"📍 [{current.x},{current.y}] | {current.name}\n\n"
        f"<i>{current.description}</i>\n"
    )
    if current.has_mob:
        text += f"\n👾 {current.mob_name} (ур. {current.mob_level})"
    if current.has_chest:
        text += "\n📦 Сундук поблизости"
    if current.has_exit:
        text += "\n🚪 Лестница вниз"

    kb = dungeon_movement_keyboard(can_dirs)
    
    # Пытаемся найти подходящую картинку для типа клетки подземелья
    from core.neutral_tiles import background_for
    from bot.utils.photos import send_or_edit_photo
    
    # DungeonCell не имеет всех полей Cell, но имеет tile_type и name
    neutral = background_for(current, []) # Передаем пустой список соседей для простоты
    image_url = None
    if neutral:
        image_url, _ = neutral
        
    await send_or_edit_photo(callback, text, reply_markup=kb, image_url=image_url)
