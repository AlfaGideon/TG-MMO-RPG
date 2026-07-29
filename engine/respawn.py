"""Восстановление мира: твари и сундуки возвращаются со временем.

Без этого мир одноразовый: убитая тварь исчезала навсегда, вскрытый сундук
не появлялся снова, и через вечер игры карта пустела насовсем.

Как устроено. Убийство не стирает тварь молча, а ставит на клетку метку
`mob_at` — время возвращения. `tick()` вызывается на шаге игрока (там же,
где `cataclysm.auto`), поэтому фоновые задачи не нужны: мир оживает ровно
тогда, когда в него кто-то смотрит.

Сундук возвращается не на своё место, а на случайную клетку локации: иначе
игроки заучили бы точки и ходили по кругу.
"""
import random
import time

from engine import data
from engine import world as W

# Сколько ждать возвращения, в минутах, по типу локации.
MOB_DELAY = {"safe": 0, "dangerous": 15, "dungeon": 30, "boss": 45}
CHEST_DELAY = {"safe": 0, "dangerous": 25, "dungeon": 40, "boss": 60}

SETTING_MOB = "respawn_mob_min"      # переопределение из панели
SETTING_CHEST = "respawn_chest_min"
SETTING_ON = "respawn_enabled"


def enabled(store):
    return bool(store.settings.get(SETTING_ON, True))


def _loc_type(loc):
    return data.LOCATIONS[loc][2] if 0 <= loc < len(data.LOCATIONS) else "dangerous"


def _minutes(store, kind, loc):
    """Задержка для локации: настройка панели или значение по типу."""
    table = MOB_DELAY if kind == "mob" else CHEST_DELAY
    key = SETTING_MOB if kind == "mob" else SETTING_CHEST
    override = (store.settings.get(key) or {}).get(_loc_type(loc))
    if override is None:
        return table.get(_loc_type(loc), 15)
    try:
        return max(0, float(override))
    except (TypeError, ValueError):
        return table.get(_loc_type(loc), 15)


# ── постановка в очередь ────────────────────────────────────

def schedule_mob(store, cell):
    """Тварь убита: наметить возвращение. В безопасных землях — никогда."""
    cell.mob = -1
    delay = _minutes(store, "mob", cell.loc)
    cell.mob_at = (time.time() + delay * 60) if delay > 0 else 0.0


def schedule_chest(store, cell):
    """Сундук вскрыт: наметить появление нового где-то в этой локации."""
    cell.chest = False
    delay = _minutes(store, "chest", cell.loc)
    cell.chest_at = (time.time() + delay * 60) if delay > 0 else 0.0


# ── возвращение ─────────────────────────────────────────────

def tick(store, rng=None):
    """Вернуть всё, чей срок вышел. Возвращает (тварей, сундуков).

    Клетки под игроками пропускаем: тварь не должна возникать прямо под
    ногами, а сундук — появляться в занятой клетке.
    """
    if not enabled(store):
        return 0, 0
    rng = rng or random
    now = time.time()
    busy = {f"{p.loc}:{p.x}:{p.y}" for p in store.players.values()}
    mobs = chests = 0

    for c in store.world.values():
        if c.mob_at and now >= c.mob_at:
            if c.key in busy or not c.passable or c.mob >= 0 or c.npc >= 0:
                c.mob_at = now + 60          # занято — заглянем через минуту
                continue
            c.mob = _pick_mob(c.loc, rng)
            c.mob_at = 0.0
            mobs += 1

    # Сундуки: метка висит на вскрытой клетке, а сокровище кладём в другую.
    for c in list(store.world.values()):
        if not c.chest_at or now < c.chest_at:
            continue
        c.chest_at = 0.0
        spot = _free_spot(store, c.loc, busy, rng)
        if spot is not None:
            spot.chest = True
            chests += 1
    if mobs or chests:
        store.save()
    return mobs, chests


def _pick_mob(loc, rng):
    """Тварь под стать локации: свои по прописке, иначе по её уровню."""
    own = [i for i, m in enumerate(data.MOBS) if m[8] == loc]
    if own:
        return rng.choice(own)
    lvl = data.LOCATIONS[loc][3] if loc < len(data.LOCATIONS) else 1
    fit = [i for i, m in enumerate(data.MOBS) if m[2] <= max(1, lvl) + 2]
    return rng.choice(fit or range(len(data.MOBS)))


def _free_spot(store, loc, busy, rng):
    """Случайная свободная клетка локации под новый сундук."""
    free = [c for c in store.world.values()
            if c.loc == loc and c.passable and not c.link and not c.chest
            and c.mob < 0 and c.npc < 0 and c.key not in busy
            and (c.x, c.y) != W.SPAWN]
    return rng.choice(free) if free else None


# ── сводка для панели ───────────────────────────────────────

def pending(store, loc=None):
    """Что сейчас в очереди на возвращение: [(клетка, вид, секунд)]."""
    now = time.time()
    out = []
    for c in store.world.values():
        if loc is not None and c.loc != int(loc):
            continue
        if c.mob_at:
            out.append((c, "mob", max(0, int(c.mob_at - now))))
        if c.chest_at:
            out.append((c, "chest", max(0, int(c.chest_at - now))))
    return sorted(out, key=lambda r: r[2])


def delays(store):
    """Текущие задержки по типам локаций — для формы настроек."""
    out = {}
    for kind, table in (("mob", MOB_DELAY), ("chest", CHEST_DELAY)):
        out[kind] = {t: _minutes(store, kind, _first_loc_of(t))
                     for t in table}
    return out


def _first_loc_of(loc_type):
    """Индекс любой локации нужного типа — чтобы прочитать её задержку."""
    for i, l in enumerate(data.LOCATIONS):
        if l[2] == loc_type:
            return i
    return 0


def set_delays(store, kind, values):
    """Сохранить задержки по типам локаций (минуты)."""
    key = SETTING_MOB if kind == "mob" else SETTING_CHEST
    saved = store.settings.setdefault(key, {})
    for loc_type, raw in values.items():
        try:
            saved[loc_type] = max(0, float(raw))
        except (TypeError, ValueError):
            continue
    store.save()
    return saved
