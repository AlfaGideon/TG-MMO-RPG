"""Игровые данные и действия приложения поверх серверного стека core/*.

Те же правила и та же база, что у Telegram-бота: хэндлеры бота — тонкая
обёртка над этими же core-модулями, поэтому прогресс в приложении и в боте
общий by design. Здесь не изобретаются новые игровые правила, только
JSON-ориентированная проекция для HTTP API.
"""
import random
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core import homestead
from core.dates import utcnow
from core.loot import give_chest_loot
from core.mob_images import mob_image_url
from core.models import Cell, Character, Location, User, VisitedCell
from core.spawns import spawn_at_cell
from engine.currency import add_currency, currency_str

# 8 направлений: те же клавиши, что в bot/handlers/location.py:DIRECTIONS
DIRECTIONS = {
    "n": (-1, 0), "s": (1, 0), "w": (0, -1), "e": (0, 1),
    "nw": (-1, -1), "ne": (-1, 1), "sw": (1, -1), "se": (1, 1),
}
DIRECTION_LABELS = {
    "n": "Север", "s": "Юг", "w": "Запад", "e": "Восток",
    "nw": "Северо-запад", "ne": "Северо-восток",
    "sw": "Юго-запад", "se": "Юго-восток",
}


class ServiceError(Exception):
    """Ожидаемая игровая ошибка — API превратит её в HTTP 400 с текстом."""


async def load_character(session: AsyncSession, user: User) -> Character | None:
    result = await session.execute(
        select(Character)
        .where(Character.user_id == user.id)
        .options(selectinload(Character.location), selectinload(Character.cell))
    )
    return result.scalar_one_or_none()


def _class_key(character: Character) -> str:
    value = character.character_class
    return getattr(value, "value", str(value))


def profile_dict(character: Character, user: User) -> dict:
    return {
        "name": character.name,
        "class": _class_key(character),
        "level": character.level,
        "experience": character.experience,
        "exp_to_next": character.level * 100,
        "hp": {"current": character.current_hp, "max": character.max_hp},
        "mp": {"current": character.current_mp, "max": character.max_mp},
        "currency": currency_str(character),
        "stats": {
            "strength": character.strength,
            "agility": character.agility,
            "intelligence": character.intelligence,
            "endurance": character.endurance,
            "luck": character.luck,
        },
        "faction": character.faction,
        "stat_points": character.stat_points or 0,
        "is_vip": bool(character.is_vip),
        "location": character.location.name if character.location else None,
        "coordinates": (
            {"x": character.cell.x, "y": character.cell.y, "floor": character.floor}
            if character.cell else None
        ),
        "telegram_id": user.telegram_id,
        "username": user.username,
    }


async def _mob_summary(session, cell: Cell) -> dict | None:
    spawn = await spawn_at_cell(session, cell)
    if not spawn or not spawn.mob:
        return None
    mob = spawn.mob
    return {
        "spawn_id": spawn.id,
        "name": mob.name,
        "level": mob.level,
        "hp": spawn.current_hp or mob.hp,
        "max_hp": mob.hp,
        "damage": mob.damage,
        "is_boss": bool(mob.is_boss),
        "image": mob_image_url(mob.name) or mob.image_url or "",
        "engaged": bool(spawn.engaged_by_id),
    }


async def cell_view(session: AsyncSession, character: Character) -> dict:
    """Текущая клетка: что на ней происходит и куда можно шагнуть."""
    cell = character.cell
    if cell is None:
        raise ServiceError("Герой ещё не помещён в мир — заверши создание в боте.")
    location = character.location

    mob = await _mob_summary(session, cell)

    # Соседние проходимые клетки — для джойстика направлений.
    neighbors = []
    for key, (dx, dy) in DIRECTIONS.items():
        target = await session.scalar(
            select(Cell)
            .where(Cell.location_id == cell.location_id)
            .where(Cell.floor == (character.floor or 0))
            .where(Cell.x == cell.x + dx)
            .where(Cell.y == cell.y + dy)
        )
        if target is not None and target.is_passable:
            neighbors.append({
                "direction": key,
                "label": DIRECTION_LABELS[key],
                "x": target.x, "y": target.y,
                "tile": target.tile_type,
                "transition": target.target_location_id is not None,
            })

    chest_ready = cell.has_chest and (
        cell.chest_respawn_at is None or cell.chest_respawn_at <= utcnow()
    )

    return {
        "location": location.name if location else "Неизвестные земли",
        "cell": {
            "name": cell.name or "",
            "description": cell.description or "",
            "x": cell.x, "y": cell.y, "floor": character.floor or 0,
            "tile": cell.tile_type,
            # Ручной фон клетки, если задан администратором; нейтральные
            # JPEG-сцены рендерит только бот — SPA рисует сцену сам по tile.
            "image": cell.image_url or "",
        },
        "mob": mob,
        "npc": (
            {"name": cell.npc_name, "dialogue": cell.npc_dialogue,
             "type": cell.npc_type, "station": cell.npc_station}
            if cell.has_npc and cell.npc_name else None
        ),
        "chest": {"ready": bool(chest_ready), "tier": cell.chest_tier or 1}
                 if cell.has_chest else None,
        "campfire": bool(cell.has_campfire),
        "house": bool(cell.has_house),
        "neighbors": neighbors,
    }


async def move(session: AsyncSession, character: Character, direction: str) -> dict:
    """Шаг на соседнюю клетку. Бесшовные переходы между локациями поддержаны
    в базовом виде: если у клетки есть target_* — прыгаем в указанную точку."""
    direction = (direction or "").lower()
    if direction not in DIRECTIONS:
        raise ServiceError("Неизвестное направление")
    if character.cell is None:
        raise ServiceError("Герой ещё не в мире")

    dx, dy = DIRECTIONS[direction]
    current = character.cell
    target = await session.scalar(
        select(Cell)
        .where(Cell.location_id == current.location_id)
        .where(Cell.floor == (character.floor or 0))
        .where(Cell.x == current.x + dx)
        .where(Cell.y == current.y + dy)
    )
    if target is None or not target.is_passable:
        raise ServiceError("Туда нельзя пройти")

    # Переход между локациями/этажами через клетку-портал.
    if target.target_location_id is not None and target.target_x is not None:
        dest = await session.scalar(
            select(Cell)
            .where(Cell.location_id == target.target_location_id)
            .where(Cell.x == target.target_x)
            .where(Cell.y == target.target_y)
        )
        if dest is None or not dest.is_passable:
            raise ServiceError("Переход ведёт в замурованную клетку")
        target = dest
        dest_location = await session.get(Location, target.location_id)
        character.location_id = target.location_id
        character.floor = target.floor or 0
        character.location = dest_location
        location_name = dest_location.name if dest_location else "новая локация"
    else:
        location_name = character.location.name if character.location else ""

    # cell_id и связь cell держим вместе: без этого следующий шаг в той же
    # сессии считался бы от старой клетки (relationship не обновляется сам).
    character.cell_id = target.id
    character.cell = target
    await _mark_visited(session, character, target)
    await session.commit()
    return {
        "ok": True,
        "message": f"Шаг на {DIRECTION_LABELS[direction].lower()}",
        "location_name": location_name,
        "cell": await cell_view(session, character),
    }


async def _mark_visited(session: AsyncSession, character: Character, cell: Cell) -> None:
    # Схема visited_cells хранит координаты, а не FK на клетку, — та же
    # проекция, что в bot/handlers/location.py:mark_visited.
    exists = await session.scalar(
        select(VisitedCell).where(
            VisitedCell.character_id == character.id,
            VisitedCell.location_id == cell.location_id,
            VisitedCell.floor == (cell.floor or 0),
            VisitedCell.x == cell.x,
            VisitedCell.y == cell.y,
        )
    )
    if exists is None:
        session.add(VisitedCell(
            character_id=character.id,
            location_id=cell.location_id,
            floor=cell.floor or 0,
            x=cell.x, y=cell.y,
        ))


async def inspect_cell(session: AsyncSession, character: Character) -> dict:
    """Осмотр: если есть готовый сундук — открываем, иначе описание клетки."""
    cell = character.cell
    if cell is None:
        raise ServiceError("Герой ещё не в мире")

    if cell.has_chest:
        if cell.chest_respawn_at and cell.chest_respawn_at > utcnow():
            raise ServiceError("Сундук уже пуст. Загляни позже.")
        new_respawn = utcnow() + timedelta(minutes=random.randint(20, 60))
        claimed = await session.execute(
            update(Cell)
            .where(Cell.id == cell.id)
            .where(Cell.has_chest.is_(True))
            .where((Cell.chest_respawn_at.is_(None)) |
                   (Cell.chest_respawn_at <= utcnow()))
            .values(chest_respawn_at=new_respawn)
        )
        if claimed.rowcount != 1:
            raise ServiceError("Сундук уже пуст. Загляни позже.")
        cell.chest_respawn_at = new_respawn

        tier = max(1, cell.chest_tier or 1)
        gold = random.randint(5 * tier, 25 * tier)
        add_currency(character, bronze=gold)
        loot = await give_chest_loot(
            session, character, cell.location_id, tier=tier
        )
        await session.commit()
        names = [inv.display_name() for inv in loot]
        return {
            "ok": True,
            "message": "Сундук открыт!",
            "gold_bronze": gold,
            "loot": names,
            "cell": await cell_view(session, character),
        }

    view = await cell_view(session, character)
    if view["mob"]:
        return {"ok": True, "message": f"Здесь враг: {view['mob']['name']}. Готовься к бою!",
                "cell": view}
    if view["npc"]:
        return {"ok": True,
                "message": f"{view['npc']['name']}: {view['npc']['dialogue'] or '...'}",
                "cell": view}
    return {"ok": True, "message": cell.description or "Пусто. Лишь ветер шевелит травы.",
            "cell": view}


async def rest(session: AsyncSession, character: Character) -> dict:
    """Отдых у костра или дома. В чистом поле отдыхать нечем."""
    cell = character.cell
    if cell is None:
        raise ServiceError("Герой ещё не в мире")
    if not (cell.has_campfire or cell.has_house or homestead.at_home(character)):
        raise ServiceError("Отдыхать можно у костра или дома.")

    share = await homestead.rest_share_for(session, character)
    heal = homestead.rest_amount(character.max_hp, share)
    mp_restore = homestead.rest_amount(character.max_mp, share)
    character.current_hp = min(character.max_hp, character.current_hp + heal)
    character.current_mp = min(character.max_mp, character.current_mp + mp_restore)
    await session.commit()
    return {
        "ok": True,
        "message": f"Отдых восстановил {heal} HP и {mp_restore} MP",
        "hp": {"current": character.current_hp, "max": character.max_hp},
        "mp": {"current": character.current_mp, "max": character.max_mp},
    }
