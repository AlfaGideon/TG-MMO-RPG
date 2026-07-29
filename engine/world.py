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

# Дефолтная раскладка стартовых пяти локаций — ряд на восток.
DEFAULT_GRID = {str(i): [i, 0] for i in range(5)}

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


def _connect(cells):
    """Отсечь недостижимые от спавна клетки."""
    passable = {(c.x, c.y): c for c in cells if c.passable}
    if SPAWN not in passable:
        for c in cells:
            if (c.x, c.y) == SPAWN:
                c.passable = True
                c.tile = "grass"
                passable[SPAWN] = c
    seen, q = {SPAWN}, deque([SPAWN])
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


def gen_cells(li, rnd, story=0, story_rnd=None):
    """Клетки одной локации li со спавном в центре. Возвращает (batch, story).

    `rnd` задаёт рельеф, `story_rnd` (если передан) — тексты клеток: разные
    сиды правят разные стороны мира независимо друг от друга.
    """
    batch = []
    for x in range(SIZE):
        for y in range(SIZE):
            border = x in (0, SIZE - 1) or y in (0, SIZE - 1)
            wall = border or (rnd.random() < 0.15 and (x, y) != SPAWN)
            if story_rnd is not None:
                name, desc, tile = story_rnd.choice(data.STORIES)
            else:
                name, desc, tile = data.STORIES[story % len(data.STORIES)]
            story += 1
            batch.append(Cell(loc=li, x=x, y=y, name=name, desc=desc,
                              tile="wall" if wall else tile, passable=not wall))
    _connect(batch)
    return batch, story


def generate(seed=1337, locations=None, grid=None, seeds=None):
    """Возвращает {key: Cell}. `grid` — {str(loc): [wx, wy]} на мировой сетке;
    если не задан, локации связываются цепочкой, как раньше.

    `seeds` — словарь частных сидов (см. SEEDS). Без него всё выводится из
    одного `seed`, как и раньше.
    """
    locs = locations if locations is not None else data.LOCATIONS
    seeds = seeds or seeds_of({"seed": seed})
    rnd = random.Random(seeds.get("terrain", seed))
    story_rnd = random.Random(seeds.get("stories", seed))
    cells, story = {}, 0
    for li in range(len(locs)):
        batch, story = gen_cells(li, rnd, story, story_rnd)
        for c in batch:
            cells[c.key] = c
    if grid:
        _link_by_grid(cells, grid)
    else:
        for a in range(len(locs) - 1):
            _link_east(cells, a, a + 1)
    _populate(cells, rnd, locs, seeds)
    return cells


# ── швы между локациями ───────────────────────────────────

def _road(c, link):
    c.passable = True
    c.tile = "road"
    c.name = "Тракт между землями"
    c.desc = "Утоптанная дорога уходит вдаль."
    c.link = link


def _link_east(cells, a, b):
    """Восточная граница A ↔ западная граница B — одна дверь в центре, а не стена."""
    mid = SIZE // 2
    _road(cells[f"{a}:{mid}:{SIZE - 1}"], (b, mid, 1))
    _road(cells[f"{b}:{mid}:0"], (a, mid, SIZE - 2))
    # дорога от центра к двери
    for x in range(1, SIZE - 1):
        c = cells.get(f"{a}:{x}:{mid}")
        if c and not c.passable:
            _road(c, c.link)
    for x in range(1, SIZE - 1):
        c = cells.get(f"{b}:{x}:{mid}")
        if c and not c.passable:
            _road(c, c.link)
    for y in range(1, SIZE - 1):
        # вертикальная ветка к двери уже включает центр
        pass


def _link_south(cells, a, b):
    """Южная граница A ↔ северная граница B — одна дверь в центре."""
    mid = SIZE // 2
    _road(cells[f"{a}:{SIZE - 1}:{mid}"], (b, 1, mid))
    _road(cells[f"{b}:0:{mid}"], (a, SIZE - 2, mid))
    for y in range(1, SIZE - 1):
        c = cells.get(f"{a}:{mid}:{y}")
        if c and not c.passable:
            _road(c, c.link)
    for y in range(1, SIZE - 1):
        c = cells.get(f"{b}:{mid}:{y}")
        if c and not c.passable:
            _road(c, c.link)


def _link_by_grid(cells, grid):
    """Швы по соседству на мировой сетке: восток/запад и север/юг."""
    pos = {int(k): tuple(v) for k, v in grid.items()}
    pairs = set()
    for ai, (ax, ay) in pos.items():
        for bi, (bx, by) in pos.items():
            if ai == bi or (bi, ai) in pairs:
                continue
            if (bx, by) == (ax + 1, ay):
                _link_east(cells, ai, bi)
                pairs.add((ai, bi))
            elif (bx, by) == (ax, ay + 1):
                _link_south(cells, ai, bi)
                pairs.add((ai, bi))


def link_new_location(cells, li, grid):
    """Вшить свежедобавленную локацию li в существующий мир.

    Граница связывается только если обе стороны свободны (ничьих швов ещё
    нет) — чужие рукоправные переходы не затираются. Возвращает отчёт.
    """
    pos = {int(k): tuple(v) for k, v in grid.items()}
    if li not in pos:
        return ["Локация не размещена на сетке мира."]
    ax, ay = pos[li]
    report = []
    dirs = {"восток": (1, 0, "e"), "запад": (-1, 0, "w"),
            "юг": (0, 1, "s"), "север": (0, -1, "n")}
    loc_name = data.LOCATIONS[li][0] if li < len(data.LOCATIONS) else str(li)
    mid = SIZE // 2
    for name, (dx, dy, side) in dirs.items():
        nb = next((j for j, (x, y) in pos.items() if (x, y) == (ax + dx, ay + dy)), None)
        if nb is None:
            continue
        if side == "e":
            mine, theirs = [(li, mid, SIZE - 1)], [(nb, mid, 0)]
        elif side == "w":
            mine, theirs = [(li, mid, 0)], [(nb, mid, SIZE - 1)]
        elif side == "s":
            mine, theirs = [(li, SIZE - 1, mid)], [(nb, 0, mid)]
        else:
            mine, theirs = [(li, 0, mid)], [(nb, SIZE - 1, mid)]
        busy = any(cells[f"{l}:{x}:{y}"].link for l, x, y in mine + theirs)
        if busy:
            report.append(f"{name}: граница с «{data.LOCATIONS[nb][0]}» уже занята швом.")
            continue
        if side == "e":
            _link_east(cells, li, nb)
        elif side == "w":
            _link_east(cells, nb, li)
        elif side == "s":
            _link_south(cells, li, nb)
        else:
            _link_south(cells, nb, li)
        report.append(f"🔗 {name} ↔ {data.LOCATIONS[nb][0]} (1 дверь)")
    if not report:
        report.append(f"Соседей у «{loc_name}» на сетке нет.")
    return report


# ── заселение ─────────────────────────────────────────────

def _populate(cells, rnd, locs=None, seeds=None):
    """Расставить NPC, мобов и сундуки по типам локаций.

    У жителей, тварей и сундуков свои сиды: можно перетряхнуть добычу,
    не трогая рельеф и расстановку мобов.
    """
    locs = locs if locs is not None else data.LOCATIONS
    seeds = seeds or {}
    npc_rnd = random.Random(seeds.get("npc")) if seeds.get("npc") else rnd
    mob_rnd = random.Random(seeds.get("mobs")) if seeds.get("mobs") else rnd
    chest_rnd = random.Random(seeds.get("chests")) if seeds.get("chests") else rnd
    free = lambda li: [c for c in cells.values()
                       if c.loc == li and c.passable and not c.link
                       and (c.x, c.y) != SPAWN and c.mob < 0 and c.npc < 0]

    # NPC — в первой безопасной локации (или в нулевой, если такой нет)
    safe = next((i for i, l in enumerate(locs) if l[2] == "safe"), 0)
    spots = free(safe)
    npc_rnd.shuffle(spots)
    for i in range(min(len(data.NPCS), len(spots))):
        spots[i].npc = i

    # Мобы — в своих локациях; если локация удалена/не создана, моб не спавнится
    for mi, m in enumerate(data.MOBS):
        li = m[8]
        if li >= len(locs):
            continue
        count = 1 if m[0] == "Пожиратель Глубин" else 4
        spots = free(li)
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


def cell_at(cells, loc, x, y):
    return cells.get(f"{loc}:{x}:{y}")


def neighbours(cells, loc, x, y):
    """{направление: проходимо?} для 8 сторон."""
    out = {}
    for d, (dx, dy) in DIRS.items():
        c = cell_at(cells, loc, x + dx, y + dy)
        out[d] = bool(c and c.passable)
    return out


DIRS = {
    "nw": (-1, -1), "n": (-1, 0), "ne": (-1, 1),
    "w": (0, -1), "e": (0, 1),
    "sw": (1, -1), "s": (1, 0), "se": (1, 1),
}

ARROWS = {"nw": "↖️", "n": "⬆️", "ne": "↗️", "w": "⬅️", "e": "➡️",
          "sw": "↙️", "s": "⬇️", "se": "↘️"}
