"""Популяция мобов на карте: спавн по лимиту и передвижение по локациям.

Правила, которые обеспечивает модуль:

* В каждой локации живёт ровно `Mob.population` экземпляров каждого моба.
  Убили одного — через `respawn_seconds` появится новый, но сверх лимита
  никто не спавнится.
* Мобы ходят по проходимым клеткам своей локации.
* Слабый моб может забрести в локацию уровнем выше, сильный к слабым —
  нет: переход разрешён только если `min_level` соседней локации не ниже
  `min_level` домашней локации моба.
"""
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from core.models import Cell, Location, Mob, MobSpawn

# Насколько «свежим» должен быть шаг, чтобы моб не телепортировался пачками
MOVE_JITTER = 0.35


def _now():
    # aware-время под timestamptz-колонки: на Postgres сравнение с naive
    # utcnow() падало, и живой мир (респавн/передвижение) молча умирал.
    return datetime.now(timezone.utc)


def _aware(dt):
    """SQLite возвращает naive, Postgres — aware; приводим к aware."""
    return dt if (dt is None or dt.tzinfo) else dt.replace(tzinfo=timezone.utc)


async def _passable_cells(session, location_id: int, floor: int = 0):
    result = await session.execute(
        select(Cell)
        .where(Cell.location_id == location_id)
        .where(Cell.floor == floor)
        .where(Cell.is_passable == True)  # noqa: E712
    )
    return result.scalars().all()


async def _pick_spawn_cell(session, location_id: int, floor: int = 0):
    cells = await _passable_cells(session, location_id, floor)
    # Не спавним на порталах, у NPC и на переходах между локациями
    free = [
        c for c in cells
        if not c.has_npc and c.dungeon_template_id is None and c.target_location_id is None
    ]
    return random.choice(free or cells) if (free or cells) else None


async def ensure_population(session, mob: Mob) -> list[MobSpawn]:
    """Досоздаёт живые экземпляры моба до его лимита популяции.

    Возвращает список созданных спавнов. Уважает `respawn_seconds`:
    убитый моб возвращается не мгновенно.
    """
    if not mob.location_id:
        return []

    limit = max(0, mob.population if mob.population is not None else 1)
    if limit == 0:
        return []

    alive = await session.scalar(
        select(func.count(MobSpawn.id))
        .where(MobSpawn.mob_id == mob.id)
        .where(MobSpawn.is_alive == True)  # noqa: E712
    ) or 0
    missing = limit - alive
    if missing <= 0:
        return []

    now = _now()
    # Сначала оживляем те трупы, у которых вышел таймер респавна
    result = await session.execute(
        select(MobSpawn)
        .where(MobSpawn.mob_id == mob.id)
        .where(MobSpawn.is_alive == False)  # noqa: E712
        .order_by(MobSpawn.respawn_at)
    )
    dead = result.scalars().all()

    # Трупы, чей таймер ещё тикает, уже «занимают место» в популяции —
    # иначе на месте только что убитого моба мгновенно вставал бы новый.
    pending = sum(1 for d in dead if d.respawn_at and _aware(d.respawn_at) > now)

    created = []
    for spawn in dead:
        if missing <= 0:
            break
        if spawn.respawn_at and _aware(spawn.respawn_at) > now:
            continue
        cell = await _pick_spawn_cell(session, mob.location_id)
        if not cell:
            break
        spawn.is_alive = True
        spawn.current_hp = mob.hp
        spawn.location_id = mob.location_id
        spawn.home_location_id = mob.location_id
        spawn.floor = cell.floor or 0
        spawn.x, spawn.y = cell.x, cell.y
        spawn.killed_at = None
        spawn.respawn_at = None
        spawn.engaged_by_id = None
        spawn.last_move_at = now
        created.append(spawn)
        missing -= 1

    # Новые записи заводим только на «свободные» слоты — те, что не заняты
    # ещё не отсчитавшими своё трупами.
    missing -= pending
    while missing > 0:
        cell = await _pick_spawn_cell(session, mob.location_id)
        if not cell:
            break
        spawn = MobSpawn(
            mob_id=mob.id,
            home_location_id=mob.location_id,
            location_id=mob.location_id,
            floor=cell.floor or 0,
            x=cell.x, y=cell.y,
            current_hp=mob.hp,
            is_alive=True,
            last_move_at=now,
        )
        session.add(spawn)
        created.append(spawn)
        missing -= 1

    if created:
        await session.flush()
    return created


async def ensure_all_populations(session) -> int:
    """Прогоняет `ensure_population` по всем мобам с привязкой к локации."""
    result = await session.execute(select(Mob).where(Mob.location_id.isnot(None)))
    total = 0
    for mob in result.scalars().all():
        total += len(await ensure_population(session, mob))
    return total


async def kill_spawn(session, spawn: MobSpawn, mob: Mob):
    """Помечает экземпляр мёртвым и заводит таймер респавна."""
    now = _now()
    spawn.is_alive = False
    spawn.current_hp = 0
    spawn.killed_at = now
    spawn.engaged_by_id = None
    delay = max(5, mob.respawn_seconds if mob.respawn_seconds is not None else 120)
    # Небольшой разброс, чтобы мобы не воскресали синхронно
    spawn.respawn_at = now + timedelta(seconds=int(delay * random.uniform(0.8, 1.25)))


async def can_roam_to(session, mob: Mob, home_location: Location, target: Location) -> bool:
    """Слабый моб может уйти «наверх», сильный к слабым — нет."""
    if target is None or home_location is None:
        return False
    if target.id == home_location.id:
        return True
    if not mob.can_roam:
        return False
    # Ключевое правило: уровень целевой локации не ниже домашней
    if (target.min_level or 1) < (home_location.min_level or 1):
        return False
    # Дальность бродяжничества по мировой сетке
    radius = max(0, mob.roam_radius or 0)
    if radius == 0:
        return False
    dist = abs((target.world_x or 0) - (home_location.world_x or 0)) + \
        abs((target.world_y or 0) - (home_location.world_y or 0))
    return dist <= radius


async def _neighbor_locations(session, location: Location):
    """Локации, соседние по мировой сетке."""
    result = await session.execute(select(Location))
    out = []
    for loc in result.scalars().all():
        if loc.id == location.id:
            continue
        dist = abs((loc.world_x or 0) - (location.world_x or 0)) + \
            abs((loc.world_y or 0) - (location.world_y or 0))
        if dist == 1:
            out.append(loc)
    return out


async def move_spawn(session, spawn: MobSpawn, mob: Mob) -> bool:
    """Один шаг моба. Возвращает True, если он сдвинулся."""
    if spawn.engaged_by_id:
        return False  # в бою моб никуда не уходит
    interval = mob.move_interval_seconds or 0
    if interval <= 0 or not mob.can_roam:
        return False

    now = _now()
    if spawn.last_move_at \
            and (now - _aware(spawn.last_move_at)).total_seconds() < interval:
        return False
    if random.random() < MOVE_JITTER:
        spawn.last_move_at = now
        return False

    home = await session.get(Location, spawn.home_location_id)
    current = await session.get(Location, spawn.location_id)

    # Иногда моб пробует уйти в соседнюю локацию (если правила позволяют)
    if random.random() < 0.12:
        for candidate in random.sample(
            await _neighbor_locations(session, current),
            k=min(2, len(await _neighbor_locations(session, current))) or 0,
        ):
            if await can_roam_to(session, mob, home, candidate):
                cell = await _pick_spawn_cell(session, candidate.id)
                if cell:
                    spawn.location_id = candidate.id
                    spawn.floor = cell.floor or 0
                    spawn.x, spawn.y = cell.x, cell.y
                    spawn.last_move_at = now
                    return True

    # Обычный шаг на соседнюю клетку в пределах текущей локации
    steps = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    random.shuffle(steps)
    for dx, dy in steps:
        result = await session.execute(
            select(Cell)
            .where(Cell.location_id == spawn.location_id)
            .where(Cell.floor == (spawn.floor or 0))
            .where(Cell.x == spawn.x + dx)
            .where(Cell.y == spawn.y + dy)
            .where(Cell.is_passable == True)  # noqa: E712
        )
        cell = result.scalar_one_or_none()
        if cell and cell.target_location_id is None and not cell.has_npc:
            spawn.x, spawn.y = cell.x, cell.y
            spawn.last_move_at = now
            return True

    spawn.last_move_at = now
    return False


async def tick(session) -> dict:
    """Один игровой тик: респавн по лимиту + передвижение живых мобов."""
    spawned = await ensure_all_populations(session)

    result = await session.execute(
        select(MobSpawn)
        .options(selectinload(MobSpawn.mob))
        .where(MobSpawn.is_alive == True)  # noqa: E712
    )
    moved = 0
    for spawn in result.scalars().all():
        if spawn.mob is None:
            continue
        if await move_spawn(session, spawn, spawn.mob):
            moved += 1

    return {"spawned": spawned, "moved": moved}


async def spawn_at_cell(session, cell: Cell):
    """Живой моб, стоящий на этой клетке (или None)."""
    result = await session.execute(
        select(MobSpawn)
        .options(selectinload(MobSpawn.mob))
        .where(MobSpawn.is_alive == True)  # noqa: E712
        .where(MobSpawn.location_id == cell.location_id)
        .where(MobSpawn.floor == (cell.floor or 0))
        .where(MobSpawn.x == cell.x)
        .where(MobSpawn.y == cell.y)
    )
    return result.scalars().first()


async def spawns_in_location(session, location_id: int, floor: int = 0):
    result = await session.execute(
        select(MobSpawn)
        .options(selectinload(MobSpawn.mob))
        .where(MobSpawn.is_alive == True)  # noqa: E712
        .where(MobSpawn.location_id == location_id)
        .where(MobSpawn.floor == floor)
    )
    return result.scalars().all()


async def population_report(session):
    """Сводка для админки: сколько живо/мертво по каждому мобу."""
    result = await session.execute(
        select(Mob).options(selectinload(Mob.location)).order_by(Mob.id)
    )
    rows = []
    for mob in result.scalars().all():
        alive = await session.scalar(
            select(func.count(MobSpawn.id))
            .where(MobSpawn.mob_id == mob.id)
            .where(MobSpawn.is_alive == True)  # noqa: E712
        ) or 0
        pending = await session.scalar(
            select(func.count(MobSpawn.id))
            .where(MobSpawn.mob_id == mob.id)
            .where(MobSpawn.is_alive == False)  # noqa: E712
        ) or 0
        rows.append({
            "mob": mob, "alive": alive, "dead": pending,
            "limit": mob.population or 0,
        })
    return rows
