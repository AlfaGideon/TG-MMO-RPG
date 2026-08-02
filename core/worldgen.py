"""Построение и преобразование мира — общая логика для сида, админки и бота.

Мир — сетка локаций на мировой карте (WORLD_GRID_SIZE×WORLD_GRID_SIZE).
Каждая локация — собственная квадратная сетка клеток (grid_size×grid_size),
возможно многоэтажная. Соседние по мировой карте локации связываются
бесшовными переходами через пограничные клетки: шаг на границу переносит
игрока в зеркальную клетку соседней локации.

Координаты клеток: x — вертикаль (север→юг), y — горизонталь (запад→восток),
как в `core/map_renderer.py`. Координаты на мировой карте: world_x — восток,
world_y — юг.
"""
import random
from collections import deque

from sqlalchemy import select, update, delete, func

from core.models import (
    Location, Cell, Character, Mob, MobSpawn, Quest, VisitedCell,
)
from core.enums import LocationType

WORLD_GRID_SIZE = 10  # 10×10 локаций на мировой карте

# Соседство на мировой карте: (Δworld_x, Δworld_y).
DIRS = {"e": (1, 0), "w": (-1, 0), "s": (0, 1), "n": (0, -1)}
OPPOSITE = {"e": "w", "w": "e", "s": "n", "n": "s"}
DIR_NAMES = {"e": "восток", "w": "запад", "s": "юг", "n": "север"}


def center_of(grid_size: int) -> tuple:
    """Центральная клетка сетки — она же спавн и узел лестниц."""
    g = max(3, int(grid_size or 10))
    return (g // 2, g // 2)


# ── связность ─────────────────────────────────────────────

def ensure_connectivity(cells, grid_size: int):
    """Гарантирует, что все проходимые клетки досягаемы из центра.

    `cells` — любые объекты с x, y, is_passable, tile_type (мутируются).
    Недосягаемое становится стеной: игрок не должен застревать в карманах.
    """
    passable = {(c.x, c.y): c for c in cells if c.is_passable}
    if not passable:
        return
    start = center_of(grid_size)
    if start not in passable:
        c = next((c for c in cells if (c.x, c.y) == start), None)
        if c:
            c.is_passable = True
            if c.tile_type == "wall":
                c.tile_type = "grass"
            passable[start] = c
    seen, queue = {start}, deque([start])
    while queue:
        x, y = queue.popleft()
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            n = (x + dx, y + dy)
            if n in passable and n not in seen:
                seen.add(n)
                queue.append(n)
    for pos, c in passable.items():
        if pos not in seen:
            c.is_passable = False
            c.tile_type = "wall"


# ── генерация клеток ──────────────────────────────────────

async def build_cells(session, loc, stories, rng=None, wall_density=0.15):
    """Создаёт клетки всех этажей локации с проверкой связности.

    Только для свежесозданных локаций (у loc ещё нет клеток).
    `stories` — список (name, description, tile) для наполнения клеток.
    """
    rng = rng or random
    cx, cy = center_of(loc.grid_size)
    story_idx = rng.randint(0, len(stories) - 1)
    for floor in range(max(1, loc.floors_count or 1)):
        cells = []
        for x in range(loc.grid_size):
            for y in range(loc.grid_size):
                border = x in (0, loc.grid_size - 1) or y in (0, loc.grid_size - 1)
                wall = border or (rng.random() < wall_density and (x, y) != (cx, cy))
                name_s, desc_s, tile = stories[story_idx % len(stories)]
                story_idx += 1
                cell = Cell(
                    location_id=loc.id, x=x, y=y, floor=floor,
                    name=name_s, description=desc_s,
                    is_passable=not wall,
                    tile_type=tile if not wall else "wall",
                )
                session.add(cell)
                cells.append(cell)
        ensure_connectivity(cells, loc.grid_size)
    await session.flush()
    if (loc.floors_count or 1) > 1:
        await ensure_stairs(session, loc)


async def ensure_stairs(session, loc):
    """Лестницы между обычными (неотрицательными) этажами.

    Одна клетка не может целиться на два этажа сразу, поэтому лестница —
    это пара соседних клеток: узел UP (в центре) ведёт на этаж выше, узел
    DOWN (соседняя) — на этаж ниже. С любого этажа можно и подняться, и
    спуститься: раньше ссылка была односторонней, и игрок застревал наверху.

    Возвращает ``True``, если что-то действительно было исправлено. Это
    нужно ленивому ремонту в боте: старые базы получают лестницы при первом
    открытии клетки, но мы не коммитим пустые изменения на каждый экран.
    """
    floors = max(1, loc.floors_count or 1)
    if floors < 2:
        return False

    changed = False
    cx, cy = center_of(loc.grid_size)
    dx, dy = (1, 0) if cx + 1 < loc.grid_size - 1 else (-1, 0)
    ux, uy, ddx, ddy = cx, cy, cx + dx, cy + dy

    def apply(cell, tx, ty, tf):
        nonlocal changed
        if not cell:
            return
        desired = {
            "is_passable": True,
            "tile_type": "road",
            "target_location_id": loc.id,
            "target_x": tx,
            "target_y": ty,
            "target_floor": tf,
        }
        for attr, value in desired.items():
            if getattr(cell, attr) != value:
                setattr(cell, attr, value)
                changed = True

    for floor in range(floors):
        if floor < floors - 1:  # узел UP: наверх
            up = await cell_at(session, loc.id, ux, uy, floor)
            apply(up, ux, uy, floor + 1)
        if floor > 0:         # узел DOWN: вниз
            down = await cell_at(session, loc.id, ddx, ddy, floor)
            apply(down, ddx, ddy, floor - 1)
    if changed:
        await session.flush()
    return changed


def _inner_coord(value: int, grid_size: int) -> int:
    """Координата внутри рамки карты, не на внешней стене."""
    g = max(3, int(grid_size or 10))
    return max(1, min(g - 2, int(value)))


def underground_stair_positions(grid_size: int) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    """Стандартные клетки подземных лестниц.

    Возвращает ``(entry_pos, down_pos, up_pos)``:

    * ``entry_pos`` — вход на поверхности (этаж 0), рядом с центром;
    * ``down_pos`` — узел спуска на подземных этажах;
    * ``up_pos`` — соседний узел подъёма на подземных этажах.

    Важно: поверхность не использует центральную клетку ``down_pos``. Она
    зарезервирована обычными этажами ``floors_count`` (замковый подвал/башни).
    Старый сид перетирал этой клеткой лестницу 0↔1, из-за чего игроки
    «падали» в отрицательные этажи и не могли вернуться.
    """
    g = max(3, int(grid_size or 10))
    cx, cy = center_of(g)
    entry = (cx, _inner_coord(cy - 1, g))
    down = (cx, cy)
    up = (_inner_coord(cx + 1, g), cy)
    if up == down:
        up = (_inner_coord(cx - 1, g), cy)
    if entry in (down, up):
        entry = (cx, _inner_coord(cy + 1, g))
    return entry, down, up


async def underground_floors(session, loc) -> list[int]:
    """Список отрицательных этажей локации: -1, -2, ..."""
    result = await session.execute(
        select(Cell.floor)
        .where(Cell.location_id == loc.id)
        .where(Cell.floor < 0)
        .distinct()
    )
    return sorted({int(row[0]) for row in result.all()}, reverse=True)


async def ensure_underground_stairs(session, loc):
    """Двусторонние лестницы для отрицательных этажей (-1, -2, ...).

    Отрицательные этажи — это именно подземелье под локацией, не часть
    ``floors_count``. Поэтому они чинятся отдельной схемой и не конфликтуют
    с обычной лестницей 0↔1.

    На каждом подземном уровне есть два соседних узла: один ведёт вниз,
    второй — вверх. На самом глубоком уровне центральный узел тоже ведёт
    вверх, чтобы вытащить персонажей, которые уже застряли на старой
    односторонней лестнице в центре.
    """
    floors = await underground_floors(session, loc)
    if not floors:
        return False

    floor_set = set(floors)
    entry_pos, down_pos, up_pos = underground_stair_positions(loc.grid_size)
    changed = False

    def apply(cell, target_pos, target_floor, name, desc):
        nonlocal changed
        if not cell:
            return
        desired = {
            "is_passable": True,
            "tile_type": "road",
            "target_location_id": loc.id,
            "target_x": target_pos[0],
            "target_y": target_pos[1],
            "target_floor": target_floor,
            "name": name,
            "description": desc,
        }
        for attr, value in desired.items():
            if getattr(cell, attr) != value:
                setattr(cell, attr, value)
                changed = True

    # Поверхностный вход в подземелье: отдельная клетка рядом с центром,
    # чтобы не перетирать обычную лестницу floor 0 -> floor 1.
    entry = await cell_at(session, loc.id, *entry_pos, 0)
    apply(
        entry, up_pos, -1,
        "Спуск в подземелье",
        "Старая лестница уходит под замок. Отсюда можно спуститься ниже.",
    )

    for floor in floors:  # -1, -2, ...
        upper_floor = floor + 1
        upper_pos = entry_pos if upper_floor == 0 else up_pos

        up_cell = await cell_at(session, loc.id, *up_pos, floor)
        if upper_floor == 0 or upper_floor in floor_set:
            apply(
                up_cell, upper_pos, upper_floor,
                "Подъём из глубин",
                "Лестница ведёт на уровень выше.",
            )

        down_cell = await cell_at(session, loc.id, *down_pos, floor)
        deeper_floor = floor - 1
        if deeper_floor in floor_set:
            apply(
                down_cell, up_pos, deeper_floor,
                "Спуск глубже",
                "Ступени уходят ещё ниже во тьму.",
            )
        else:
            # Самое дно: раньше здесь оставалась ссылка в несуществующий
            # этаж (например, -2 -> -3), из-за чего кнопка была ловушкой.
            # Делаем центр запасным подъёмом для уже застрявших игроков.
            if upper_floor == 0 or upper_floor in floor_set:
                apply(
                    down_cell, upper_pos, upper_floor,
                    "Подъём из глубин",
                    "Дальше вниз проход завален; лестница ведёт обратно наверх.",
                )

    if changed:
        await session.flush()
    return changed


async def cell_at(session, location_id, x, y, floor=0):
    result = await session.execute(
        select(Cell)
        .where(Cell.location_id == location_id)
        .where(Cell.floor == floor)
        .where(Cell.x == x).where(Cell.y == y)
    )
    return result.scalar_one_or_none()


async def _cells_by_pos(session, loc, floor=0):
    result = await session.execute(
        select(Cell).where(Cell.location_id == loc.id).where(Cell.floor == floor)
    )
    return {(c.x, c.y): c for c in result.scalars().all()}


# ── соседи и швы ──────────────────────────────────────────

async def neighbor(session, loc, direction):
    """Сосед loc на мировой карте в направлении direction (e/w/s/n) или None."""
    dx, dy = DIRS[direction]
    wx, wy = loc.world_x + dx, loc.world_y + dy
    if not (0 <= wx < WORLD_GRID_SIZE and 0 <= wy < WORLD_GRID_SIZE):
        return None
    result = await session.execute(
        select(Location).where(Location.world_x == wx).where(Location.world_y == wy)
    )
    nb = result.scalar_one_or_none()
    return nb if nb and nb.id != loc.id else None


async def link_pair(session, a, b, direction):
    """Бесшовный переход между a и b; b находится со стороны `direction` от a.

    Ворота — ОДНА клетка в центре границы, а не стена из дверей.
    После линковки прорубаем дорогу от центра каждой локации к этим
    воротам, чтобы переход никогда не упирался в стену.
    Возвращает 1 (одна пара ворот).
    """
    mid_a = a.grid_size // 2
    mid_b = b.grid_size // 2

    if direction == "e":
        ca_pos = (mid_a, a.grid_size - 1)
        cb_pos = (mid_b, 0)
        ta = (mid_b, 1)
        tb = (mid_a, a.grid_size - 2)
    elif direction == "w":
        ca_pos = (mid_a, 0)
        cb_pos = (mid_b, b.grid_size - 1)
        ta = (mid_b, b.grid_size - 2)
        tb = (mid_a, 1)
    elif direction == "s":
        ca_pos = (a.grid_size - 1, mid_a)
        cb_pos = (0, mid_b)
        ta = (1, mid_b)
        tb = (a.grid_size - 2, mid_a)
    else:  # "n"
        ca_pos = (0, mid_a)
        cb_pos = (b.grid_size - 1, mid_b)
        ta = (b.grid_size - 2, mid_b)
        tb = (1, mid_a)

    ca = await cell_at(session, a.id, *ca_pos)
    cb = await cell_at(session, b.id, *cb_pos)
    if ca:
        ca.is_passable = True
        ca.tile_type = "road"
        ca.target_location_id, ca.target_x, ca.target_y, ca.target_floor = b.id, *ta, 0
    if cb:
        cb.is_passable = True
        cb.tile_type = "road"
        cb.target_location_id, cb.target_x, cb.target_y, cb.target_floor = a.id, *tb, 0

    await _carve_single(session, a, direction, mid_a)
    await _carve_single(session, b, OPPOSITE[direction], mid_b)
    await session.flush()
    return 1


async def _carve_single(session, loc, direction, mid):
    """Дорога от центра локации к единственному переходу в сторону direction.

    mid — индекс ряда/колонны ворот (центр границы).
    Делаем хребет через центр и одну ветку к границе, чтобы гарантировать
    проходимость. Стены становятся дорогой; содержимое клеток не трогаем.
    """
    cells = await _cells_by_pos(session, loc)
    cx, cy = center_of(loc.grid_size)

    def open_(x, y):
        c = cells.get((x, y))
        if c and not c.is_passable:
            c.is_passable = True
            c.tile_type = "road"

    if direction in ("e", "w"):
        for x in range(1, loc.grid_size - 1):
            open_(x, cy)
        border_y = loc.grid_size - 1 if direction == "e" else 0
        lo, hi = sorted((cy, border_y))
        for y in range(lo, hi + 1):
            open_(mid, y)
    else:
        for y in range(1, loc.grid_size - 1):
            open_(cx, y)
        border_x = loc.grid_size - 1 if direction == "s" else 0
        lo, hi = sorted((cx, border_x))
        for x in range(lo, hi + 1):
            open_(x, mid)


# ═══════════════════════════════════════════════════════════
# Угловые замки: 25×25, замки по углам, NPC внутри, мобы снаружи
# ═══════════════════════════════════════════════════════════

async def build_corner_castle(session, loc, stories, rng=None, npcs=None):
    """Генерирует угловую локацию 25×25 с замками по углам.

    Разбивка 25 = 10 + 5 + 10: в четырёх углах сетки — замки 10×10
    (безопасные клетки «village», там живут NPC), крест шириной 5 между
    ними — опасные пустоши (туда селятся мобы) и решётка дорог (ряды и
    колонны 10/12/14), в центре — площадь. Каждый замок примыкает
    к дороге, поэтому все четыре достижимы; недостижимое становится стеной.

    `npcs` — 4 списка (по числу замков) кортежей (имя, диалог, тип):
    жители расставляются на свободных клетках внутри своих замков.
    """
    rng = rng or random
    size = max(25, int(loc.grid_size or 25))
    cx, cy = size // 2, size // 2
    s = size
    b = s // 2 - 3                         # 9: последний ряд углового квартала
    blocks = [((0, b), (0, b)),            # северо-западный замок 10×10
              ((0, b), (s - b - 1, s - 1)),   # северо-восточный
              ((s - b - 1, s - 1), (0, b)),   # юго-западный
              ((s - b - 1, s - 1), (s - b - 1, s - 1))]  # юго-восточный

    def in_block(x, y):
        return any(x0 <= x <= x1 and y0 <= y <= y1
                   for (x0, x1), (y0, y1) in blocks)

    def open_(by_pos, x, y):
        c = by_pos.get((x, y))
        if c and not c.is_passable:
            c.is_passable = True
            c.tile_type = "road"
            c.name, c.description = "Тракт", "Утоптанная дорога между замками."

    for floor in range(max(1, loc.floors_count or 1)):
        cells = []
        for x in range(size):
            for y in range(size):
                is_center = abs(x - cx) <= 2 and abs(y - cy) <= 2
                border = x == 0 or x == size - 1 or y == 0 or y == size - 1
                if in_block(x, y):
                    wall = False
                    tile = "village"
                    name_s, desc_s = "Замок", "Каменные стены замка. Здесь безопасно."
                elif is_center:
                    wall = False
                    tile = "grass"
                    name_s, desc_s = "Центральная площадь", "Площадь с патрулями."
                elif border:
                    is_door = (x == cx and y in (0, size - 1)) or (y == cy and x in (0, size - 1))
                    wall = not is_door
                    tile = "wall" if wall else "road"
                    name_s, desc_s = ("Ворота" if is_door else "Стена",
                                      "Ворота замка." if is_door else "Глухая стена.")
                else:
                    wall = rng.random() < 0.3
                    tile = "grass" if not wall else "wall"
                    name_s, desc_s = ("Пустошь", "Опасная земля между замками."
                                      if not wall else "Скала.")
                cell = Cell(
                    location_id=loc.id, x=x, y=y, floor=floor,
                    name=name_s, description=desc_s,
                    is_passable=not wall,
                    tile_type=tile,
                )
                session.add(cell)
                cells.append(cell)
        by_pos = {(c.x, c.y): c for c in cells}
        # Решётка дорог: ряды и колонны 10, 12, 14 — от ворот к воротам.
        # Каждый замок 10×10 примыкает к дороге своей стороной.
        for row in (b + 1, cx, b + 3):
            for y in range(1, s - 1):
                open_(by_pos, row, y)
        for col in (b + 1, cy, b + 3):
            for x in range(1, s - 1):
                open_(by_pos, x, col)
        # Площадь остаётся площадью, а не перекрёстком дорог.
        for x in range(cx - 2, cx + 3):
            for y in range(cy - 2, cy + 3):
                c = by_pos.get((x, y))
                if c:
                    c.is_passable = True
                    c.tile_type = "grass"
                    c.name, c.description = "Центральная площадь", "Площадь с патрулями."
        ensure_connectivity(cells, size)
        # Жители по замкам: по одному на свободную клетку цитадели.
        # `npcs` — 4 списка кортежей (имя, диалог, тип); одиночный кортеж
        # принимается как список из одного жителя.
        if npcs:
            for bi in range(min(4, len(npcs))):
                castle_npcs = npcs[bi]
                if castle_npcs and isinstance(castle_npcs[0], str):
                    castle_npcs = [castle_npcs]
                x0, x1 = blocks[bi][0]
                y0, y1 = blocks[bi][1]
                spot = [c for c in cells
                        if x0 <= c.x <= x1 and y0 <= c.y <= y1
                        and c.is_passable and not c.has_npc]
                rng.shuffle(spot)
                for i, (npc_name, dialogue, npc_type) in enumerate(castle_npcs):
                    if i >= len(spot):
                        break
                    spot[i].has_npc = True
                    spot[i].npc_name = npc_name
                    spot[i].npc_dialogue = dialogue
                    spot[i].npc_type = npc_type
    await session.flush()


# ═══════════════════════════════════════════════════════════
# Соседи по миру — одиночные двери (уже исправлено выше)
# ═══════════════════════════════════════════════════════════


# Обратная совместимость
async def _carve_to_border(session, loc, direction, gates):
    mid = loc.grid_size // 2
    await _carve_single(session, loc, direction, mid)


async def autolink(session, loc):
    """Связывает loc со всеми соседями по мировой карте. Одиночная дверь в центре границы."""
    report = []
    for d in ("n", "e", "s", "w"):
        nb = await neighbor(session, loc, d)
        if not nb:
            continue
        await unlink_others(session, loc)
        gates = await link_pair(session, loc, nb, d)
        report.append(f"🔗 {DIR_NAMES[d]} ↔ {nb.name} ({gates} дверь)")
    if not report:
        report.append("Соседей на мировой карте нет — связывать не с кем.")
    return report


async def unlink_others(session, loc):
    """Убирает переходы между loc и другими локациями (лестницы не трогаем).

    Клетки-швы остаются проходимыми дорогами, но уже никуда не ведут.
    """
    await session.execute(
        update(Cell)
        .where(Cell.location_id == loc.id)
        .where(Cell.target_location_id != loc.id)
        .values(target_location_id=None, target_x=None, target_y=None, target_floor=None)
    )
    await session.execute(
        update(Cell)
        .where(Cell.target_location_id == loc.id)
        .where(Cell.location_id != loc.id)
        .values(target_location_id=None, target_x=None, target_y=None, target_floor=None)
    )


async def relink_all(session):
    """Пересобирает все бесшовные швы по текущим мировым координатам.

    Вызывать после перемещений локаций: старые швы снимаются, новые
    ставятся по фактическому соседству на сетке WORLD_GRID_SIZE×WORLD_GRID_SIZE.
    """
    result = await session.execute(select(Location))
    locations = result.scalars().all()
    for loc in locations:
        await unlink_others(session, loc)
    await session.flush()
    done = set()
    pairs = []
    for loc in locations:
        for d in ("e", "s"):  # каждой паре достаточно одной стороны
            nb = await neighbor(session, loc, d)
            if nb and (nb.id, loc.id) not in done:
                pairs.append((loc, nb, d))
                done.add((loc.id, nb.id))
    for a, b, d in pairs:
        await link_pair(session, a, b, d)
    return len(pairs)
