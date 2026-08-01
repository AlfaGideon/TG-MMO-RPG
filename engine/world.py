"""Генерация бесшовного мира: локации по 10×10 клеток, швы по мировой сетке.

Локации берутся из `data.LOCATIONS` (список может быть динамическим — его
подменяет `engine/storage.py` из настроек панели). Переходы между локациями
строятся по соседству на мировой сетке `world_grid` ({индекс: [wx, wy]}):
соседи по горизонтали сшиваются восток↔запад, по вертикали — север↔юг.
Без сетки работает старая цепочка 0→1→2→… — для совместимости.
"""
import random
from collections import deque

from engine import data
from engine.models import Cell

SIZE = 10
SPAWN = (5, 5)

# Угловые замки — локации 25×25 с цитаделями по углам (см. gen_castle_cells).
# {индекс локации: размер сетки}
DEFAULT_SIZES = {"5": 25, "6": 25, "7": 25, "8": 25}

# Дефолтная раскладка мира — вся мировая карта 10×10.
# По краям — 36 локаций: 4 угла занимают замки 25×25, между ними по 8
# опасных трактов на каждую сторону (промежуточные локации между углами).
# Внутри кольца — стартовые земли и Логово Пожирателя.
DEFAULT_GRID = {
    # ── стартовые земли (внутри кольца) ──
    "0": [4, 4],   # Погост Костров
    "1": [5, 4],   # Тёмный Лес
    "2": [5, 5],   # Заброшенная Крепость
    "3": [4, 5],   # Катакомбы Павших
    "4": [3, 4],   # Логово Пожирателя
    # ── угловые замки 25×25 по углам мировой карты ──
    "5": [0, 0],   # Замок Рассвета (северо-запад)
    "6": [9, 0],   # Замок Теней (северо-восток)
    "7": [0, 9],   # Замок Глубин (юго-запад)
    "8": [9, 9],   # Замок Пепла (юго-восток)
    # ── тракты по краям: 8 на каждую сторону ──
    "9":  [1, 0], "10": [2, 0], "11": [3, 0], "12": [4, 0],
    "13": [5, 0], "14": [6, 0], "15": [7, 0], "16": [8, 0],   # север
    "17": [9, 1], "18": [9, 2], "19": [9, 3], "20": [9, 4],
    "21": [9, 5], "22": [9, 6], "23": [9, 7], "24": [9, 8],   # восток
    "25": [8, 9], "26": [7, 9], "27": [6, 9], "28": [5, 9],
    "29": [4, 9], "30": [3, 9], "31": [2, 9], "32": [1, 9],   # юг
    "33": [0, 8], "34": [0, 7], "35": [0, 6], "36": [0, 5],
    "37": [0, 4], "38": [0, 3], "39": [0, 2], "40": [0, 1],   # запад
}

# Сиды мира: у каждой стороны генерации свой, чтобы правка одного не
# перетряхивала всё остальное. (ключ, подпись, за что отвечает, множитель)
SEEDS = [
    ("terrain",   "🗺 Рельеф",     "стены, тропы и форма локаций",      31),
    ("stories",   "📖 Описания",   "названия и тексты клеток",          97),
    ("mobs",      "👾 Мобы",       "расстановка тварей по клеткам",     193),
    ("chests",    "📦 Сундуки",    "где лежит добыча",                  389),
    ("npc",       "💬 NPC",        "места жителей в безопасных землях", 769),
    ("cataclysm", "🌋 Катаклизмы", "череда бедствий и их размах",       1543),
]
SEED_KEYS = [k for k, _, _, _ in SEEDS]
SEED_LABELS = {k: lbl for k, lbl, _, _ in SEEDS}
SEED_ABOUT = {k: about for k, _, about, _ in SEEDS}
_SEED_MUL = {k: mul for k, _, _, mul in SEEDS}


def seeds_of(settings):
    """Все сиды мира: явно заданные в панели или выведенные из базового.

    Один «Seed» остаётся главным: пока частные сиды не тронуты, они
    выводятся из него, и мир целиком воспроизводим по одному числу.
    """
    base = int(settings.get("seed", 1337) or 0)
    saved = settings.get("seeds") or {}
    out = {}
    for key in SEED_KEYS:
        raw = saved.get(key)
        try:
            val = int(raw)
        except (TypeError, ValueError):
            val = 0
        out[key] = val or ((base * _SEED_MUL[key] + len(key) * 7919) % 2_147_483_647)
    return out


def _connect(cells, start=SPAWN):
    """Отсечь недостижимые от центра клетки."""
    passable = {(c.x, c.y): c for c in cells if c.passable}
    if start not in passable:
        for c in cells:
            if (c.x, c.y) == start:
                c.passable = True
                c.tile = "grass"
                passable[start] = c
    seen, q = {start}, deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            n = (x + dx, y + dy)
            if n in passable and n not in seen:
                seen.add(n)
                q.append(n)
    for pos, c in passable.items():
        if pos not in seen:
            c.passable = False
            c.tile = "wall"


def gen_cells(li, rnd, story=0, story_rnd=None, size=SIZE):
    """Клетки одной локации li со спавном в центре. Возвращает (batch, story).

    `rnd` задаёт рельеф, `story_rnd` (если передан) — тексты клеток: разные
    сиды правят разные стороны мира независимо друг от друга. `size` —
    сторона квадратной сетки (10 по умолчанию).
    """
    batch = []
    cx, cy = size // 2, size // 2
    for x in range(size):
        for y in range(size):
            border = x in (0, size - 1) or y in (0, size - 1)
            wall = border or (rnd.random() < 0.15 and (x, y) != (cx, cy))
            if story_rnd is not None:
                name, desc, tile = story_rnd.choice(data.STORIES)
            else:
                name, desc, tile = data.STORIES[story % len(data.STORIES)]
            story += 1
            batch.append(Cell(loc=li, x=x, y=y, name=name, desc=desc,
                              tile="wall" if wall else tile, passable=not wall))
    _connect(batch, (cx, cy))
    return batch, story


def is_castle(locs, li):
    """Угловой замок: безопасная локация с именем «Замок …» и размером 25×25."""
    try:
        return bool(locs[li][2] == "safe" and str(locs[li][0]).startswith("Замок"))
    except (IndexError, TypeError):
        return False


def gen_castle_cells(li, rnd, size=25, story_rnd=None):
    """Клетки углового замка 25×25: в четырёх углах — замки 10×10
    с жителями, между ними — опасные пустоши с мобами.

    Разбивка 25 = 10 + 5 + 10: угловые кварталы 10×10 — замки (village,
    безопасно, там NPC), крест шириной 5 между ними — пустоши и дороги
    (твари), в центре — площадь. Дороги образуют решётку (ряды и колонны
    10/12/14), поэтому из каждого замка есть путь к центру, а двери на
    границах — одна в середине, как у обычных локаций: бесшовные
    переходы работают для любого размера.
    """
    batch = []
    cx, cy = size // 2, size // 2          # 12, 12
    s = size
    b = s // 2 - 3                         # 9: последний ряд углового квартала
    blocks = [((0, b), (0, b)),            # северо-западный замок 10×10
              ((0, b), (s - b - 1, s - 1)),   # северо-восточный
              ((s - b - 1, s - 1), (0, b)),   # юго-западный
              ((s - b - 1, s - 1), (s - b - 1, s - 1))]  # юго-восточный

    def in_block(x, y):
        return any(x0 <= x <= x1 and y0 <= y <= y1
                   for (x0, x1), (y0, y1) in blocks)

    for x in range(s):
        for y in range(s):
            if in_block(x, y):
                wall, tile = False, "village"
                name, desc = "Замок", "Каменные стены замка. Здесь безопасно."
            elif abs(x - cx) <= 2 and abs(y - cy) <= 2:
                wall, tile = False, "grass"
                name, desc = "Центральная площадь", "Площадь с патрулями."
            elif x in (0, s - 1) or y in (0, s - 1):
                is_door = ((x == cx and y in (0, s - 1)) or
                           (y == cy and x in (0, s - 1)))
                wall = not is_door
                tile = "wall" if wall else "road"
                name = "Ворота" if is_door else "Стена"
                desc = "Ворота замка." if is_door else "Глухая стена."
            else:
                wall = rnd.random() < 0.3
                tile = "wall" if wall else "grass"
                name = "Пустошь"
                desc = ("Опасная земля между замками." if not wall
                        else "Скала.")
            batch.append(Cell(loc=li, x=x, y=y, name=name, desc=desc,
                              tile=tile, passable=not wall))

    def open_(x, y):
        c = next((c for c in batch if c.x == x and c.y == y), None)
        if c and not c.passable:
            c.passable = True
            c.tile = "road"
            c.name, c.desc = "Тракт", "Утоптанная дорога между замками."

    # Решётка дорог: ряды и колонны 10, 12, 14 — от ворот к воротам.
    # Каждый замок 10×10 примыкает к дороге своей стороной.
    for row in (b + 1, cx, b + 3):
        for y in range(1, s - 1):
            open_(row, y)
    for col in (b + 1, cy, b + 3):
        for x in range(1, s - 1):
            open_(x, col)
    # Площадь остаётся площадью, а не перекрёстком дорог.
    for x in range(cx - 2, cx + 3):
        for y in range(cy - 2, cy + 3):
            c = next(c for c in batch if c.x == x and c.y == y)
            c.tile = "grass"
            c.passable = True
            c.name, c.desc = "Центральная площадь", "Площадь с патрулями."
    _connect(batch, (cx, cy))
    return batch, 0


def generate(seed=1337, locations=None, grid=None, seeds=None, floors=None,
             sizes=None):
    """Возвращает {key: Cell}. `grid` — {str(loc): [wx, wy]} на мировой сетке;
    если не задан, локации связываются цепочкой, как раньше.

    `seeds` — словарь частных сидов (см. SEEDS). Без него всё выводится из
    одного `seed`, как и раньше. `sizes` — {loc: размер сетки} для локаций,
    чей размер отличается от стандартного (угловые замки 25×25).
    """
    locs = locations if locations is not None else data.LOCATIONS
    seeds = seeds or seeds_of({"seed": seed})
    rnd = random.Random(seeds.get("terrain", seed))
    story_rnd = random.Random(seeds.get("stories", seed))
    cells, story = {}, 0
    floors = floors or {}
    sizes = sizes or {}
    for li in range(len(locs)):
        size = _size_of(sizes, li)
        count = max(1, int(floors.get(str(li), floors.get(li, 1)) or 1))
        for floor in range(count):
            batch, story = (gen_castle_cells(li, rnd, size, story_rnd)
                            if is_castle(locs, li) else
                            gen_cells(li, rnd, story, story_rnd, size))
            for c in batch:
                c.floor = floor
                cells[c.key] = c
        # Лестницы ставятся на двух соседних проходимых клетках и ведут
        # в соседний этаж. Они симметричны и всегда доступны с обеих сторон.
        for floor in range(count - 1):
            # На промежуточном этаже лестница вверх и вниз стоят на
            # соседних клетках: обе стороны перехода остаются доступны.
            stair_y = size // 2 + floor
            a = (cells.get(f"{li}:{size // 2}:{stair_y}") if floor == 0 else
                 cells.get(f"{li}:{floor}:{size // 2}:{stair_y}"))
            b = cells.get(f"{li}:{floor + 1}:{size // 2}:{stair_y}")
            if a is None or b is None:
                continue
            a.link = (li, size // 2, stair_y, floor + 1)
            b.link = (li, size // 2, stair_y, floor)
            a.name = "Лестница вниз"
            b.name = "Лестница вверх"
            a.desc = "Каменная лестница ведёт ниже."
            b.desc = "Лестница ведёт наверх."
            a.tile = b.tile = "road"
    if grid:
        _link_by_grid(cells, grid, sizes)
    else:
        for a in range(len(locs) - 1):
            _link_east(cells, a, a + 1, sizes)
    _populate(cells, rnd, locs, seeds, sizes)
    return cells


# ── швы между локациями ───────────────────────────────────

def _road(c, link):
    c.passable = True
    c.tile = "road"
    c.name = "Тракт между землями"
    c.desc = "Утоптанная дорога уходит вдаль."
    c.link = link


def _size_of(sizes, li, default=SIZE):
    if not sizes:
        return default
    return max(3, int(sizes.get(li, sizes.get(str(li), default)) or default))


def _carve_road(cells, li, size, row, col_from, col_to):
    """Прорубить дорогу вдоль ряда `row` от col_from до col_to (включительно)."""
    for y in range(min(col_from, col_to), max(col_from, col_to) + 1):
        c = cells.get(f"{li}:{row}:{y}")
        if c and not c.passable:
            _road(c, c.link)


def _carve_road_col(cells, li, size, col, row_from, row_to):
    """Прорубить дорогу вдоль колонны `col` от row_from до row_to (включительно)."""
    for x in range(min(row_from, row_to), max(row_from, row_to) + 1):
        c = cells.get(f"{li}:{x}:{col}")
        if c and not c.passable:
            _road(c, c.link)


def _link_east(cells, a, b, sizes=None):
    """Восточная граница A ↔ западная граница B — одна дверь в центре, а не стена.

    Дорога от центра к воротам идёт ВДОЛЬ ряда ворот (x = mid): раньше
    здесь прорубали колонну, и дверь на восточной границе оставалась
    за стеной — перейти было некуда.
    """
    sa, sb = _size_of(sizes, a), _size_of(sizes, b)
    mid_a, mid_b = sa // 2, sb // 2
    _road(cells[f"{a}:{mid_a}:{sa - 1}"], (b, mid_b, 1))
    _road(cells[f"{b}:{mid_b}:0"], (a, mid_a, sa - 2))
    # дорога от центра к двери — тот же ряд, что и ворота
    _carve_road(cells, a, sa, mid_a, 1, sa - 2)
    _carve_road(cells, b, sb, mid_b, 1, sb - 2)


def _link_south(cells, a, b, sizes=None):
    """Южная граница A ↔ северная граница B — одна дверь в центре.

    Дорога от центра к воротам идёт ВДОЛЬ колонны ворот (y = mid) — до
    исправления прорубали ряд, и южные ворота упирались в стену.
    """
    sa, sb = _size_of(sizes, a), _size_of(sizes, b)
    mid_a, mid_b = sa // 2, sb // 2
    _road(cells[f"{a}:{sa - 1}:{mid_a}"], (b, 1, mid_b))
    _road(cells[f"{b}:0:{mid_b}"], (a, sa - 2, mid_a))
    _carve_road_col(cells, a, sa, mid_a, 1, sa - 2)
    _carve_road_col(cells, b, sb, mid_b, 1, sb - 2)


def _link_by_grid(cells, grid, sizes=None):
    """Швы по соседству на мировой сетке: восток/запад и север/юг."""
    pos = {int(k): tuple(v) for k, v in grid.items()}
    pairs = set()
    for ai, (ax, ay) in pos.items():
        for bi, (bx, by) in pos.items():
            if ai == bi or (bi, ai) in pairs:
                continue
            if (bx, by) == (ax + 1, ay):
                _link_east(cells, ai, bi, sizes)
                pairs.add((ai, bi))
            elif (bx, by) == (ax, ay + 1):
                _link_south(cells, ai, bi, sizes)
                pairs.add((ai, bi))


def link_new_location(cells, li, grid, sizes=None):
    """Вшить свежедобавленную локацию li в существующий мир.

    Граница связывается только если обе стороны свободны (ничьих швов ещё
    нет) — чужие рукоправные переходы не затираются. Возвращает отчёт.
    `sizes` — {loc: размер сетки} (угловые замки 25×25).
    """
    pos = {int(k): tuple(v) for k, v in grid.items()}
    if li not in pos:
        return ["Локация не размещена на сетке мира."]
    ax, ay = pos[li]
    report = []
    dirs = {"восток": (1, 0, "e"), "запад": (-1, 0, "w"),
            "юг": (0, 1, "s"), "север": (0, -1, "n")}
    loc_name = data.LOCATIONS[li][0] if li < len(data.LOCATIONS) else str(li)
    sa = _size_of(sizes, li)
    mid_a = sa // 2
    for name, (dx, dy, side) in dirs.items():
        nb = next((j for j, (x, y) in pos.items() if (x, y) == (ax + dx, ay + dy)), None)
        if nb is None:
            continue
        sb = _size_of(sizes, nb)
        mid_b = sb // 2
        if side == "e":
            mine, theirs = [(li, mid_a, sa - 1)], [(nb, mid_b, 0)]
        elif side == "w":
            mine, theirs = [(li, mid_a, 0)], [(nb, mid_b, sb - 1)]
        elif side == "s":
            mine, theirs = [(li, sa - 1, mid_a)], [(nb, 0, mid_b)]
        else:
            mine, theirs = [(li, 0, mid_a)], [(nb, sb - 1, mid_b)]
        busy = any(cells.get(f"{l}:{x}:{y}") and cells[f"{l}:{x}:{y}"].link
                   for l, x, y in mine + theirs)
        if busy:
            report.append(f"{name}: граница с «{data.LOCATIONS[nb][0]}» уже занята швом.")
            continue
        if side == "e":
            _link_east(cells, li, nb, sizes)
        elif side == "w":
            _link_east(cells, nb, li, sizes)
        elif side == "s":
            _link_south(cells, li, nb, sizes)
        else:
            _link_south(cells, nb, li, sizes)
        report.append(f"🔗 {name} ↔ {data.LOCATIONS[nb][0]} (1 дверь)")
    if not report:
        report.append(f"Соседей у «{loc_name}» на сетке нет.")
    return report


# ── заселение ─────────────────────────────────────────────

def _populate(cells, rnd, locs=None, seeds=None, sizes=None):
    """Расставить NPC, мобов и сундуки по типам локаций.

    У жителей, тварей и сундуков свои сиды: можно перетряхнуть добычу,
    не трогая рельеф и расстановку мобов. Заказчики заданий живут в
    деревне, остальные жители — по угловым замкам.
    """
    locs = locs if locs is not None else data.LOCATIONS
    seeds = seeds or {}
    sizes = sizes or {}
    npc_rnd = random.Random(seeds.get("npc")) if seeds.get("npc") else rnd
    mob_rnd = random.Random(seeds.get("mobs")) if seeds.get("mobs") else rnd
    chest_rnd = random.Random(seeds.get("chests")) if seeds.get("chests") else rnd

    def center(li):
        s = _size_of(sizes, li)
        return (s // 2, s // 2)

    def free(li):
        cx, cy = center(li)
        return [c for c in cells.values()
                if c.loc == li and c.passable and not c.link
                and (c.x, c.y) != (cx, cy) and c.mob < 0 and c.npc < 0]

    # NPC — по безопасным локациям: деревня держит заказчиков заданий,
    # кузнеца, лекаря и картографа (первые шесть жителей), остальные —
    # «странствующие» — расходятся по угловым замкам (по два-три на замок).
    safe_locs = [i for i, l in enumerate(locs) if l[2] == "safe"] or [0]
    npc_list = list(data.NPCS)
    village = safe_locs[0]
    spots = free(village)
    npc_rnd.shuffle(spots)
    for i in range(min(6, len(npc_list), len(spots))):
        spots[i].npc = i
    rest = npc_list[6:]
    castles = [i for i in safe_locs if i != village and is_castle(locs, i)]
    if castles:
        for n in range(len(rest)):
            castle = castles[n % len(castles)]
            spot = [c for c in free(castle) if c.tile == "village"]
            if not spot:
                spot = free(castle)
            if not spot:
                continue
            npc_rnd.shuffle(spot)
            spot[0].npc = n + 6
    elif rest:
        spots = free(village)
        npc_rnd.shuffle(spots)
        for i in range(min(len(rest), len(spots))):
            spots[i].npc = i + 6

    # Мобы — в своих локациях; если локация удалена/не создана, моб не спавнится.
    # В угловых замках твари живут в пустошах между замками 10×10, а не
    # внутри цитаделей.
    def mob_spots(li):
        if is_castle(locs, li):
            return [c for c in free(li) if c.tile != "village"]
        return free(li)

    for mi, m in enumerate(data.MOBS):
        li = m[8]
        if li >= len(locs):
            continue
        count = 1 if m[0] == "Пожиратель Глубин" else 4
        spots = mob_spots(li)
        mob_rnd.shuffle(spots)
        for c in spots[:count]:
            c.mob = mi

    # Сундуки — во всех опасных локациях (dangerous/dungeon/boss)
    for li, l in enumerate(locs):
        if l[2] in ("dangerous", "dungeon", "boss"):
            spots = free(li)
            chest_rnd.shuffle(spots)
            for c in spots[:5]:
                c.chest = True


def cell_at(cells, loc, x, y, floor=0):
    key = f"{loc}:{x}:{y}" if not floor else f"{loc}:{floor}:{x}:{y}"
    return cells.get(key)


def neighbours(cells, loc, x, y, floor=0):
    """{направление: проходимо?} для 8 сторон."""
    out = {}
    for d, (dx, dy) in DIRS.items():
        c = cell_at(cells, loc, x + dx, y + dy, floor)
        out[d] = bool(c and c.passable)
    return out


DIRS = {
    "nw": (-1, -1), "n": (-1, 0), "ne": (-1, 1),
    "w": (0, -1), "e": (0, 1),
    "sw": (1, -1), "s": (1, 0), "se": (1, 1),
}

ARROWS = {"nw": "↖️", "n": "⬆️", "ne": "↗️", "w": "⬅️", "e": "➡️",
          "sw": "↙️", "s": "⬇️", "se": "↘️"}
