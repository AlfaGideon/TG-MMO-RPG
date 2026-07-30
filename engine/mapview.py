"""Карта локации для игрока: плитки-эмодзи и туман войны.

Никаких «#», «.», «@» — карта собирается из цветных квадратов, а неисследованные
клетки скрыты туманом. Игрок открывает мир, проходя по нему.
"""
from engine import data
from engine import world as W
from engine.models import Reply

TILE = {
    "grass": "🟩",
    "forest": "🌲",
    "road": "🟧",
    "water": "🟦",
    "wall": "⬛",
    "village": "🏠",
    "cave": "🟪",
}

FOG = "⬜"        # не исследовано
PLAYER = "🔴"     # ты
OTHER = "🔵"      # другой герой
DOOR = "🚪"       # переход в соседнюю локацию
PORTAL = "🌀"     # открытый портал в подземелье
CHEST = "📦"
MOB = "👾"
NPC = "💬"
GRAVE = "🪦"      # чьё-то надгробие с золотом
MARK = "❇️"       # неизученная достопримечательность


def ckey(loc, x, y):
    return f"{loc}:{x}:{y}"


def mark_visited(p, loc=None, x=None, y=None):
    """Отмечает клетку как исследованную вместе с соседями (радиус обзора 1)."""
    loc = p.loc if loc is None else loc
    x = p.x if x is None else x
    y = p.y if y is None else y
    seen = set(getattr(p, "visited", []) or [])
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            nx, ny = x + dx, y + dy
            if 0 <= nx < W.SIZE and 0 <= ny < W.SIZE:
                seen.add(ckey(loc, nx, ny))
    p.visited = sorted(seen)


def is_visited(p, loc, x, y):
    return ckey(loc, x, y) in set(getattr(p, "visited", []) or [])


def others_here(store, p, loc=None, x=None, y=None):
    """Другие герои в клетке. Пустой список, если хранилища нет."""
    if store is None:
        return []
    loc = p.loc if loc is None else loc
    return [q for q in store.players.values()
            if q.created_char and q.tg_id != p.tg_id and q.loc == loc
            and (x is None or (q.x == x and q.y == y))]


def other_keys(store, p):
    """{ключ клетки: [герои]} — где сейчас стоят остальные в этой локации."""
    out = {}
    for q in others_here(store, p):
        out.setdefault(ckey(q.loc, q.x, q.y), []).append(q)
    return out


def _mark_keys(store, p):
    """Неизученные достопримечательности: изученные больше не мигают."""
    if store is None:
        return set()
    from engine import landmarks
    seen = set(getattr(p, "landmarks", None) or [])
    return landmarks.keys(store) - seen


def _grave_keys(store):
    if store is None:
        return set()
    from engine import death
    return death.keys(store)


def portal_keys(store):
    """Ключи клеток, где сейчас открыты порталы подземелий."""
    out = {}
    for tpl in store.settings.get("dungeon_templates", []) or []:
        key = tpl.get("portal_cell")
        if key:
            out[key] = tpl
    return out


def glyph(cell, portals=(), graves=(), marks=()):
    """Символ клетки на карте (без учёта тумана и позиции игрока)."""
    if cell is None or not cell.passable:
        return TILE["wall"]
    if cell.key in graves:
        return GRAVE
    if cell.key in marks:
        return MARK
    if cell.key in portals:
        return PORTAL
    if cell.link:
        return DOOR
    if cell.mob >= 0:
        return MOB
    if cell.npc >= 0:
        return NPC
    if cell.chest:
        return CHEST
    return TILE.get(cell.tile, TILE["grass"])


def grid(p, cells, portals=(), others=None, graves=(), marks=()):
    """Список строк карты текущей локации игрока.

    `others` — {ключ: [герои]}: соседи видны синей точкой, но только в уже
    изученных клетках, иначе карта выдавала бы содержимое тумана.
    """
    others = others or {}
    rows = []
    for x in range(W.SIZE):
        row = ""
        for y in range(W.SIZE):
            if (x, y) == (p.x, p.y):
                row += PLAYER
                continue
            if not is_visited(p, p.loc, x, y):
                row += FOG
                continue
            if others.get(ckey(p.loc, x, y)):
                row += OTHER
                continue
            row += glyph(cells.get(ckey(p.loc, x, y)), portals, graves, marks)
        rows.append(row)
    return rows


def render(p, cells, store=None):
    """Reply с картой локации: туман войны, легенда, прогресс исследования."""
    portals = portal_keys(store) if store is not None else {}
    others = other_keys(store, p) if store is not None else {}
    graves = _grave_keys(store)
    marks = _mark_keys(store, p)
    rows = grid(p, cells, portals, others, graves, marks)

    total = sum(1 for c in cells.values() if c.loc == p.loc)
    seen = sum(1 for k in (getattr(p, "visited", []) or []) if k.startswith(f"{p.loc}:"))
    pct = int(seen / total * 100) if total else 0

    loc = data.LOCATIONS[p.loc] if p.loc < len(data.LOCATIONS) else ("Неизвестность",)
    legend = (f"{PLAYER} ты · {OTHER} герой · {FOG} не изучено · "
              f"{TILE['wall']} стена · {DOOR} переход\n"
              f"{PORTAL} портал · {MOB} враг · {NPC} житель · {CHEST} сундук · "
              f"{GRAVE} могила · {MARK} диковина")

    nearby = len(others)
    company = f" · {OTHER} рядом героев: {nearby}" if nearby else ""
    found_marks = ""
    if store is not None:
        from engine import landmarks
        fnd, allm = landmarks.total(store, p)
        if allm:
            found_marks = f" · {MARK} {fnd}/{allm}"
    text = (f"🗺 <b>{loc[0]}</b>\n"
            f"📍 Ты на [{p.x},{p.y}] · изучено {seen}/{total} ({pct}%)"
            f"{company}{found_marks}\n\n"
            + "\n".join(rows) + "\n\n" + legend)

    return Reply(text=text, keyboard=[
        [("🔄 Обновить", "map"), ("🧭 Назад в мир", "world")],
        [("◀️ Меню", "menu")],
    ])
