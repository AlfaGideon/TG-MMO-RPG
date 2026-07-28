"""Операции над миром: перемещение, resize, диагностика, безопасное удаление.

Надстройка над `core/worldgen.py` для админ-панели. Все функции принимают
открытую сессию и не коммитят — транзакцией владеет вызывающий маршрут.
"""
from collections import deque

from sqlalchemy import select, update, delete, func

from core.enums import LocationType
from core.models import (
    Location, Cell, Character, Mob, MobSpawn, Quest, VisitedCell,
)
from core import worldgen as W


# ── координаты на мировой карте ───────────────────────────

async def world_occupant(session, wx, wy, exclude_id=None):
    """Локация, занимающая клетку (wx, wy) мировой карты, или None."""
    result = await session.execute(
        select(Location).where(Location.world_x == wx).where(Location.world_y == wy)
    )
    for loc in result.scalars().all():
        if loc.id != exclude_id:
            return loc
    return None


async def find_free_spot(session):
    """Первая свободная клетка мировой карты (обход по спирали от центра)."""
    taken = set()
    result = await session.execute(select(Location.world_x, Location.world_y))
    for x, y in result.all():
        taken.add((x, y))
    c = W.WORLD_GRID_SIZE // 2
    for wx in range(W.WORLD_GRID_SIZE):
        for wy in range(W.WORLD_GRID_SIZE):
            pos = ((c + wx) % W.WORLD_GRID_SIZE, (c + wy) % W.WORLD_GRID_SIZE)
            if pos not in taken:
                return pos
    return None


async def move_location(session, loc, wx, wy):
    """Переставить локацию на (wx, wy); при коллизии — обмен местами.

    Возвращает (ok, message). Перелинковку швов вызывающий делает сам
    (обычно `W.relink_all`) после серии перемещений.
    """
    wx = max(0, min(W.WORLD_GRID_SIZE - 1, int(wx)))
    wy = max(0, min(W.WORLD_GRID_SIZE - 1, int(wy)))
    if (wx, wy) == (loc.world_x, loc.world_y):
        return True, "Локация уже стоит на этом месте."
    occupant = await world_occupant(session, wx, wy, exclude_id=loc.id)
    if occupant:
        occupant.world_x, occupant.world_y = loc.world_x, loc.world_y
        loc.world_x, loc.world_y = wx, wy
        return True, (f"🔀 Клетка была занята — обмен местами: "
                      f"«{occupant.name}» теперь на [{occupant.world_x},{occupant.world_y}].")
    loc.world_x, loc.world_y = wx, wy
    return True, f"Локация перемещена на [{wx},{wy}]."


# ── resize ────────────────────────────────────────────────

async def resize(session, loc, new_size=None, new_floors=None, stories=None):
    """Реальная смена grid_size / floors_count с миграцией клеток.

    Расширение доращивает клетки-стены по краям; обрезка запрещена, если в
    зоне стоят игроки или ведут чужие переходы. После смены размера швы
    пересобираются. Возвращает (ok, message).
    """
    from core.seed import CELL_STORIES
    stories = stories or CELL_STORIES
    new_size = int(new_size or loc.grid_size)
    new_floors = max(1, int(new_floors or loc.floors_count or 1))
    new_size = max(5, min(25, new_size))
    changed = new_size != loc.grid_size or new_floors != (loc.floors_count or 1)
    if not changed:
        return True, "Размеры не изменились."

    old_size = loc.grid_size
    old_floors = loc.floors_count or 1

    if new_size < old_size:
        # обрезать можно только если в зоне нет игроков
        result = await session.execute(
            select(Character).where(Character.location_id == loc.id)
        )
        chars = result.scalars().all()
        cells_all = await _all_cells(session, loc.id)
        by_id = {c.id: c for c in cells_all}
        stuck = [ch for ch in chars
                 if ch.cell_id and by_id.get(ch.cell_id)
                 and (by_id[ch.cell_id].x >= new_size or by_id[ch.cell_id].y >= new_size)]
        if stuck:
            return False, (f"Нельзя обрезать: в зоне {new_size}×{new_size} стоят игроки "
                           f"({', '.join(c.name for c in stuck)}). Сначала отведите их в центр.")
        inbound = await session.scalar(
            select(func.count(Cell.id))
            .where(Cell.location_id != loc.id)
            .where(Cell.target_location_id == loc.id)
            .where((Cell.target_x >= new_size) | (Cell.target_y >= new_size))
        )
        if inbound:
            return False, ("На обрезаемые клетки ведут переходы из других локаций. "
                           "Пересоберите швы или сначала уменьшите соседние локации.")

    # ── применить к клеткам ──
    if new_size < old_size:
        await session.execute(
            delete(Cell).where(Cell.location_id == loc.id)
            .where((Cell.x >= new_size) | (Cell.y >= new_size))
        )
    elif new_size > old_size:
        existing = {(c.x, c.y) for c in await _all_cells(session, loc.id)}
        idx = 0
        for floor in range(old_floors):
            for x in range(new_size):
                for y in range(new_size):
                    if (x, y) in existing or (x < old_size and y < old_size):
                        continue
                    border = x in (0, new_size - 1) or y in (0, new_size - 1)
                    name_s, desc_s, tile = stories[idx % len(stories)]
                    idx += 1
                    session.add(Cell(
                        location_id=loc.id, x=x, y=y, floor=floor,
                        name=name_s, description=desc_s,
                        is_passable=not border,
                        tile_type="wall" if border else tile,
                    ))
        await session.flush()

    if new_floors > old_floors:
        existing = {(c.x, c.y, c.floor) for c in await _all_cells(session, loc.id)}
        idx = 0
        for floor in range(old_floors, new_floors):
            cells = []
            for x in range(new_size):
                for y in range(new_size):
                    if (x, y, floor) in existing:
                        continue
                    border = x in (0, new_size - 1) or y in (0, new_size - 1)
                    name_s, desc_s, tile = stories[idx % len(stories)]
                    idx += 1
                    c = Cell(location_id=loc.id, x=x, y=y, floor=floor,
                             name=name_s, description=desc_s,
                             is_passable=not border,
                             tile_type="wall" if border else tile)
                    session.add(c)
                    cells.append(c)
            W.ensure_connectivity(cells, new_size)
        await session.flush()
    elif new_floors < old_floors:
        stuck = await session.scalar(
            select(func.count(Character.id))
            .where(Character.location_id == loc.id)
            .where(Character.floor >= new_floors)
        )
        if stuck:
            return False, f"На удаляемых этажах ({new_floors}+) стоят игроки ({stuck} чел.)."
        await session.execute(
            delete(Cell).where(Cell.location_id == loc.id).where(Cell.floor >= new_floors)
        )

    loc.grid_size = new_size
    loc.floors_count = new_floors
    await session.flush()

    # лестницы, связность и швы — по новой геометрии
    await W.ensure_stairs(session, loc)
    await _heal_connectivity(session, loc)
    await W.unlink_others(session, loc)
    await W.autolink(session, loc)
    return True, f"Размер изменён: сетка {new_size}×{new_size}, этажей {new_floors}. Швы пересобраны."


async def _all_cells(session, location_id):
    result = await session.execute(select(Cell).where(Cell.location_id == location_id))
    return result.scalars().all()


# ── диагностика и починка ─────────────────────────────────

async def _heal_connectivity(session, loc):
    """Стены в недосягаемых карманах (BFS от центра) для всех этажей."""
    fixed = 0
    for floor in range(max(1, loc.floors_count or 1)):
        cells = await _all_cells_floor(session, loc.id, floor)
        before = sum(1 for c in cells if c.is_passable)
        W.ensure_connectivity(cells, loc.grid_size)
        fixed += before - sum(1 for c in cells if c.is_passable)
    await session.flush()
    return fixed


async def _all_cells_floor(session, location_id, floor):
    result = await session.execute(
        select(Cell).where(Cell.location_id == location_id).where(Cell.floor == floor)
    )
    return result.scalars().all()


async def validate(session, loc):
    """Диагностика локации. Возвращает список (уровень, сообщение):
    уровень — 'err' (критично), 'warn' (стоит починить), 'ok'."""
    issues = []

    occupant = await world_occupant(session, loc.world_x, loc.world_y, exclude_id=loc.id)
    if occupant:
        issues.append(("err", f"Коллизия координат: здесь же стоит «{occupant.name}». "
                              "Переместите одну из локаций."))

    for floor in range(max(1, loc.floors_count or 1)):
        cells = await _all_cells_floor(session, loc.id, floor)
        by_pos = {(c.x, c.y): c for c in cells}
        missing = loc.grid_size * loc.grid_size - len(cells)
        if missing:
            issues.append(("err", f"Этаж {floor}: не хватает {missing} клеток сетки."))
        passable = {p for p, c in by_pos.items() if c.is_passable}
        start = W.center_of(loc.grid_size)
        if start in by_pos and not by_pos[start].is_passable:
            issues.append(("warn", f"Этаж {floor}: центр (спавн) непроходим."))
        # BFS
        seen, q = set(), deque([start if start in passable else next(iter(passable), None)])
        if q[0]:
            seen.add(q[0])
        while q:
            x, y = q.popleft()
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                n = (x + dx, y + dy)
                if n in passable and n not in seen:
                    seen.add(n)
                    q.append(n)
        orphan = passable - seen
        if orphan:
            issues.append(("warn", f"Этаж {floor}: {len(orphan)} недосягаемых проходимых клеток."))
        # переходы: цель должна существовать и быть проходимой
        for c in cells:
            if c.target_location_id is None:
                continue
            if c.target_x is None or c.target_y is None:
                issues.append(("err", f"Этаж {floor}: клетка [{c.x},{c.y}] — переход без координат цели."))
                continue
            t_floor = c.target_floor or 0
            if c.target_location_id == loc.id:
                target = by_pos.get((c.target_x, c.target_y)) if t_floor == floor else None
                if target is None:
                    tcells = await _all_cells_floor(session, loc.id, t_floor)
                    target = next((t for t in tcells
                                   if t.x == c.target_x and t.y == c.target_y), None)
                if target is None or not target.is_passable:
                    issues.append(("err", f"Этаж {floor}: лестница [{c.x},{c.y}] ведёт в стену/пустоту."))
            else:
                target = await W.cell_at(session, c.target_location_id,
                                         c.target_x, c.target_y, t_floor)
                if target is None:
                    issues.append(("err", f"Этаж {floor}: [{c.x},{c.y}] — висячий переход "
                                          "(клетка цели не существует)."))
                elif not target.is_passable:
                    issues.append(("warn", f"Этаж {floor}: [{c.x},{c.y}] — переход в непроходимую клетку."))
                elif target.target_location_id is None:
                    # вход есть, обратного шва нет — односторонний переход
                    issues.append(("warn", f"Этаж {floor}: [{c.x},{c.y}] — односторонний переход "
                                           "(обратного шва нет)."))

    for d in ("n", "e", "s", "w"):
        nb = await W.neighbor(session, loc, d)
        if not nb:
            continue
        linked = await session.scalar(
            select(func.count(Cell.id)).where(Cell.location_id == loc.id)
            .where(Cell.target_location_id == nb.id)
        )
        if not linked:
            issues.append(("warn", f"Сосед «{nb.name}» ({W.DIR_NAMES[d]}) не связан переходом."))

    if not issues:
        issues.append(("ok", "Проблем не найдено: связность, швы и координаты в порядке."))
    return issues


async def autofix(session, loc):
    """Чинит то, что чинится автоматически. Возвращает отчёт."""
    report = []
    fixed = await _heal_connectivity(session, loc)
    if fixed > 0:
        report.append(f"🧱 Замуровано {fixed} недосягаемых клеток-карманов.")
    await W.ensure_stairs(session, loc)
    report.append("🪜 Лестницы между этажами сделаны двусторонними.")
    links = await W.autolink(session, loc)
    report.extend(links)
    return report


# ── зависимости и удаление ────────────────────────────────

async def deps(session, loc):
    """Кто зависит от локации: для страницы подтверждения удаления."""
    players = (await session.execute(
        select(Character).where(Character.location_id == loc.id))).scalars().all()
    mobs = (await session.execute(
        select(Mob).where(Mob.location_id == loc.id))).scalars().all()
    spawns = await session.scalar(
        select(func.count(MobSpawn.id)).where(
            (MobSpawn.home_location_id == loc.id) | (MobSpawn.location_id == loc.id))) or 0
    quests = (await session.execute(
        select(Quest).where(Quest.location_id == loc.id))).scalars().all()
    inbound = await session.scalar(
        select(func.count(Cell.id)).where(Cell.location_id != loc.id)
        .where(Cell.target_location_id == loc.id)) or 0
    visited = await session.scalar(
        select(func.count(VisitedCell.id)).where(VisitedCell.location_id == loc.id)) or 0
    return {"players": players, "mobs": mobs, "spawns": spawns,
            "quests": quests, "inbound": inbound, "visited": visited}


async def fallback_location(session, exclude_id):
    """Куда эвакуировать: первая безопасная локация, иначе любая другая."""
    result = await session.execute(
        select(Location).where(Location.id != exclude_id).order_by(Location.id))
    others = result.scalars().all()
    if not others:
        return None
    return next((l for l in others if l.location_type == LocationType.SAFE), others[0])


async def spawn_cell_of(session, loc):
    """Центральная проходимая клетка локации (этаж 0)."""
    cx, cy = W.center_of(loc.grid_size)
    c = await W.cell_at(session, loc.id, cx, cy, 0)
    if c and c.is_passable:
        return c
    cells = await _all_cells_floor(session, loc.id, 0)
    passable = [c for c in cells if c.is_passable]
    if not passable:
        return None
    return min(passable, key=lambda c: abs(c.x - cx) + abs(c.y - cy))


async def safe_delete(session, loc):
    """Удаляет локацию, зачищая все ссылки. Возвращает (ok, отчёт)."""
    fallback = await fallback_location(session, loc.id)
    if not fallback:
        return False, "Это последняя локация в мире — удалять нельзя."
    target = await spawn_cell_of(session, fallback)
    if not target:
        return False, f"В «{fallback.name}» нет проходимых клеток для эвакуации."

    report = []
    players = (await session.execute(
        select(Character).where(Character.location_id == loc.id))).scalars().all()
    for ch in players:
        ch.location_id = fallback.id
        ch.cell_id = target.id
        ch.floor = 0
    if players:
        report.append(f"👥 Игроки ({len(players)}) эвакуированы в «{fallback.name}».")

    mobs = (await session.execute(
        select(Mob).where(Mob.location_id == loc.id))).scalars().all()
    for m in mobs:
        m.location_id = fallback.id
    if mobs:
        report.append(f"👾 Мобы ({len(mobs)}) приписаны к «{fallback.name}».")
    spawns = await session.scalar(
        select(func.count(MobSpawn.id))
        .where((MobSpawn.home_location_id == loc.id) | (MobSpawn.location_id == loc.id))) or 0
    await session.execute(
        delete(MobSpawn).where(
            (MobSpawn.home_location_id == loc.id) | (MobSpawn.location_id == loc.id)))
    if spawns:
        report.append(f"💨 Живые спавны ({spawns}) распущены — популяция восполнится сама.")

    quests = await session.scalar(
        select(func.count(Quest.id)).where(Quest.location_id == loc.id)) or 0
    await session.execute(
        update(Quest).where(Quest.location_id == loc.id).values(location_id=None))
    if quests:
        report.append(f"📜 Квесты ({quests}) отвязаны от локации.")

    inbound = await session.scalar(
        select(func.count(Cell.id)).where(Cell.location_id != loc.id)
        .where(Cell.target_location_id == loc.id)) or 0
    await session.execute(
        update(Cell).where(Cell.location_id != loc.id)
        .where(Cell.target_location_id == loc.id)
        .values(target_location_id=None, target_x=None, target_y=None, target_floor=None))
    if inbound:
        report.append(f"🚪 Чужие переходы ({inbound}), ведущие сюда, закрыты.")

    await session.execute(
        delete(VisitedCell).where(VisitedCell.location_id == loc.id))
    await session.execute(delete(Location).where(Location.id == loc.id))
    report.append(f"🗑 Локация «{loc.name}» удалена вместе с клетками.")
    return True, "\n".join(report)
