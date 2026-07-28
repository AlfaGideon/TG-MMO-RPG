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
DOOR = "🚪"       # переход в соседнюю локацию
PORTAL = "🌀"     # открытый портал в подземелье
CHEST = "📦"
MOB = "👾"
NPC = "💬"


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


def portal_keys(store):
    """Ключи клеток, где сейчас открыты порталы подземелий."""
    out = {}
    for tpl in store.settings.get("dungeon_templates", []) or []:
        key = tpl.get("portal_cell")
        if key:
            out[key] = tpl
    return out


def glyph(cell, portals=()):
    """Символ клетки на карте (без учёта тумана и позиции игрока)."""
    if cell is None or not cell.passable:
        return TILE["wall"]
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


def grid(p, cells, portals=()):
    """Список строк карты текущей локации игрока."""
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
            row += glyph(cells.get(ckey(p.loc, x, y)), portals)
        rows.append(row)
    return rows


def render(p, cells, store=None):
    """Reply с картой локации: туман войны, легенда, прогресс исследования."""
    portals = portal_keys(store) if store is not None else {}
    rows = grid(p, cells, portals)

    total = sum(1 for c in cells.values() if c.loc == p.loc)
    seen = sum(1 for k in (getattr(p, "visited", []) or []) if k.startswith(f"{p.loc}:"))
    pct = int(seen / total * 100) if total else 0

    loc = data.LOCATIONS[p.loc] if p.loc < len(data.LOCATIONS) else ("Неизвестность",)
    legend = (f"{PLAYER} ты · {FOG} не изучено · {TILE['wall']} стена · {DOOR} переход\n"
              f"{PORTAL} портал · {MOB} враг · {NPC} житель · {CHEST} сундук")

    text = (f"🗺 <b>{loc[0]}</b>\n"
            f"📍 Ты на [{p.x},{p.y}] · изучено {seen}/{total} ({pct}%)\n\n"
            + "\n".join(rows) + "\n\n" + legend)

    return Reply(text=text, keyboard=[
        [("🔄 Обновить", "map"), ("🧭 Назад в мир", "world")],
        [("◀️ Меню", "menu")],
    ])
