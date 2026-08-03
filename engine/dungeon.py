"""Подземелья для браузерного стека: портал наконец ведёт внутрь.

Раньше `portal_cell` был чистой декорацией — админ открывал портал, на
карте появлялся 🌀, игрокам уходила весть, а войти было некуда. Серверный
бот (`bot/handlers/dungeon.py`) подземелья умел, браузерный — нет.

Здесь та же модель, что на сервере, но в терминах `engine`:
  • «забег» (`run`) живёт у игрока в `p.dungeon` — шаблон, сид, этаж, где
    стоит и что уже зачищено;
  • сетка **не хранится**, а восстанавливается из сида по требованию, так
    что сохранение не пухнет от сотен клеток;
  • изменения (убитая тварь, вскрытый сундук) держим списком ключей.

Выход — клетка входа: пришёл своим ходом, вышел своим ходом. Смерть внутри
выбрасывает наружу, как обычная гибель.
"""
import random

from engine import data, itemui, rules
from engine.models import Reply

SIZE_DEFAULT = 10
FLOOR_TILES = ("cave", "road", "grass")
EXIT = (0, 0)                # клетка выхода — всегда угол

# Куски описаний: подземелье должно читаться, а не быть сеткой букв.
ROOMS = [
    ("Сырой коридор", "Со стен капает. Эхо шагов уходит слишком далеко."),
    ("Обвалившийся зал", "Потолок просел, из завала торчат балки."),
    ("Костница", "Черепа сложены в стены аккуратными рядами."),
    ("Затопленная галерея", "Вода по щиколотку и пахнет железом."),
    ("Зал с колоннами", "Колонны уходят во тьму, конца им не видно."),
    ("Келья", "Кто-то жил здесь добровольно. Это хуже всего."),
    ("Склад", "Ящики вскрыты, содержимое растащили давно."),
    ("Алтарная", "На камне бурые пятна, которые никто не смыл."),
    ("Провал", "Пол обрывается в темноту. Дна не слышно."),
    ("Тупик", "Дальше только стена. И царапины на ней."),
]


# ── доступ к шаблонам ───────────────────────────────────────

def templates(store):
    return store.settings.get("dungeon_templates", []) or []


def template(store, tpl_id):
    for t in templates(store):
        if int(t["id"]) == int(tpl_id):
            return t
    return None


def portal_at(store, key):
    """Шаблон, чей портал открыт в этой клетке (или None)."""
    for t in templates(store):
        if t.get("portal_cell") == key:
            return t
    return None


# ── забег ───────────────────────────────────────────────────

def run_of(p):
    r = getattr(p, "dungeon", None)
    return r if isinstance(r, dict) and r else None


def inside(p):
    return run_of(p) is not None


def size_of(tpl):
    try:
        return max(5, min(20, int(tpl.get("grid_size", SIZE_DEFAULT))))
    except (TypeError, ValueError):
        return SIZE_DEFAULT


def enter(store, p):
    """Войти в портал под ногами."""
    if inside(p):
        return view(store, p)
    key = f"{p.loc}:{p.x}:{p.y}"
    tpl = portal_at(store, key)
    if tpl is None:
        return Reply(alert="Здесь нет портала.")
    if p.level < int(tpl.get("min_level", 1)):
        return Reply(alert=f"Нужен {tpl['min_level']} уровень, у тебя {p.level}.")

    p.dungeon = {
        "tpl": int(tpl["id"]),
        "seed": random.randint(1, 1_000_000),
        "floor": 1,
        "x": EXIT[0], "y": EXIT[1],
        "back": [int(p.loc), int(p.x), int(p.y)],   # куда вернуть на выходе
        "cleared": [], "looted": [], "seen": [],
    }
    store.save_player(p)
    r = view(store, p)
    r.alert = f"Ты входишь в «{tpl['name']}»"
    return r


def leave(store, p, reason=""):
    """Выйти наружу: вернуть игрока к порталу."""
    run = run_of(p)
    if run is None:
        return Reply(alert="Ты не в подземелье.")
    back = run.get("back") or [0, 5, 5]
    p.loc, p.x, p.y = int(back[0]), int(back[1]), int(back[2])
    p.dungeon = {}
    store.save_player(p)
    text = reason or "🚪 Ты выбираешься наружу. Свежий воздух непривычен."
    return Reply(text=text, keyboard=[[("🧭 В мир", "world")], [("◀️ Меню", "menu")]])


def bail_out(store, p):
    """Аварийный выход: зовётся при гибели внутри подземелья."""
    run = run_of(p)
    if run is None:
        return
    p.dungeon = {}


# ── процедурная сетка ───────────────────────────────────────

def _cell_rng(run, x, y):
    """Своя случайность на клетку — сетка не хранится, а выводится."""
    return random.Random(run["seed"] * 7919 + run["floor"] * 104729
                         + x * 31 + y * 17)


def cell(store, p, x=None, y=None):
    """Описание клетки подземелья: восстанавливается из сида."""
    run = run_of(p)
    if run is None:
        return None
    tpl = template(store, run["tpl"]) or {}
    size = size_of(tpl)
    x = run["x"] if x is None else x
    y = run["y"] if y is None else y
    if not (0 <= x < size and 0 <= y < size):
        return None

    rng = _cell_rng(run, x, y)
    floor = int(run["floor"])
    key = f"{floor}:{x}:{y}"
    is_exit = (x, y) == EXIT
    # Выход стоит в углу: хотя бы два ближайших коридора обязаны быть
    # открыты, иначе иногда герой появлялся в комнате без единой кнопки
    # движения и подземелье выглядело зависшим.
    entry_corridor = (x, y) in {(0, 1), (1, 0)}
    wall = (not is_exit and not entry_corridor) and rng.random() < 0.20

    name, desc = ROOMS[rng.randrange(len(ROOMS))]
    mob = (not wall and not is_exit and rng.random() < 0.22
           and key not in (run.get("cleared") or []))
    chest = (not wall and not is_exit and rng.random() < 0.12
             and key not in (run.get("looted") or []))
    stairs = (not wall and not is_exit and rng.random() < 0.04)

    return {
        "x": x, "y": y, "key": key, "name": name, "desc": desc,
        "wall": wall, "exit": is_exit, "mob": mob, "chest": chest,
        "stairs": stairs, "size": size, "floor": floor,
        "mob_level": max(1, int(tpl.get("min_level", 1)) + floor - 1
                         + rng.randrange(0, 3)),
    }


def _passable(store, p, x, y):
    c = cell(store, p, x, y)
    return c is not None and not c["wall"]


# ── перемещение ─────────────────────────────────────────────

DIRS = {"n": (-1, 0), "s": (1, 0), "w": (0, -1), "e": (0, 1)}
ARROWS = {"n": "⬆️", "s": "⬇️", "w": "⬅️", "e": "➡️"}


def move(store, p, direction):
    run = run_of(p)
    if run is None:
        return Reply(alert="Ты не в подземелье.")
    dx, dy = DIRS.get(direction, (0, 0))
    nx, ny = run["x"] + dx, run["y"] + dy
    if not _passable(store, p, nx, ny):
        return Reply(alert="Там глухая стена.")
    run["x"], run["y"] = nx, ny
    seen = run.setdefault("seen", [])
    key = f"{run['floor']}:{nx}:{ny}"
    if key not in seen:
        seen.append(key)
    store.save_player(p)

    c = cell(store, p)
    if c and c["mob"]:                       # твари нападают сами
        return fight(store, p)
    return view(store, p)


def descend(store, p):
    """Спуск на следующий этаж: глубже — опаснее и прибыльнее."""
    run = run_of(p)
    c = cell(store, p) if run else None
    if not c or not c["stairs"]:
        return Reply(alert="Здесь нет спуска.")
    run["floor"] = int(run["floor"]) + 1
    run["x"], run["y"] = EXIT
    run["seen"] = []
    store.save_player(p)
    r = view(store, p)
    r.alert = f"Ты спускаешься на этаж {run['floor']}"
    return r


# ── содержимое клеток ───────────────────────────────────────

def fight(store, p):
    """Бой с обитателем подземелья — через обычную боевую систему."""
    from engine import combat

    run = run_of(p)
    c = cell(store, p) if run else None
    if not c or not c["mob"]:
        return Reply(alert="Здесь пусто.")
    run.setdefault("cleared", []).append(c["key"])
    store.save_player(p)
    idx = _mob_for(c["mob_level"])
    return combat.start(p, idx, store=store)


def _mob_for(level):
    """Тварь по уровню: берём ближайшую по силе из бестиария."""
    best, gap = 0, None
    for i, m in enumerate(data.MOBS):
        d = abs(int(m[2]) - int(level))
        if gap is None or d < gap:
            best, gap = i, d
    return best


def open_chest(store, p):
    run = run_of(p)
    c = cell(store, p) if run else None
    if not c or not c["chest"]:
        return Reply(alert="Сундука здесь нет.")
    run.setdefault("looted", []).append(c["key"])

    floor = int(run["floor"])
    gold = random.randint(15, 45) + floor * 12
    p.gold += gold
    lines = [f"📦 <b>Сундук подземелья</b>\n\nВнутри: {gold} 🪙"]

    if random.random() < 0.6:
        from engine import items
        idx = _loot_for(p)
        p.inventory.append(idx)
        inst = items.create(store, idx, source="dungeon", owner=p.tg_id,
                            luck=p.luck, detail=f"этаж {floor}")
        it = rules.item(idx)
        name = items.title(inst) if inst else it["name"]
        lines.append(f"🕳 Добыча: {it['icon']} <b>{name}</b>")

    from engine import factions
    lines.extend(factions.award(store, p, "chest_opened"))
    store.save_player(p)
    r = view(store, p)
    r.text = "\n".join(lines) + "\n\n" + r.text
    return r


def _loot_for(p):
    pool = [i for i, it in enumerate(data.ITEMS) if it[3] <= 40 + p.level * 30]
    return random.choice(pool or range(len(data.ITEMS)))


# Экраны живут в engine/dungeonui.py — здесь только правила.

def view(store, p):
    from engine import dungeonui
    return dungeonui.view(store, p)


def minimap(store, p):
    from engine import dungeonui
    return dungeonui.minimap(store, p)
