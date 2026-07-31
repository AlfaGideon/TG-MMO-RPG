"""Характеры тварей: мир перестаёт быть статичным.

Раньше все мобы были неотличимы — стояли на своих клетках вечно и ждали,
пока на них наступят. Агрессия появлялась только в катаклизм.

Теперь у каждой твари свой нрав (`data.MOBS[9]`):

  passive     — как раньше: ждёт на месте;
  territorial — не сходит с клетки, но бросается на подошедшего вплотную;
  hunter      — бродит по округе и сам идёт на игрока за пару клеток.

Катаклизм не отменяется, а накладывается сверху: он поднимает шансы
охоты для всех и остаётся пиком опасности.
"""
import random

from engine import cataclysm, data
from engine import world as W

# Насколько далеко тварь замечает игрока и с каким шансом нападает.
REACH = {"passive": 0, "territorial": 1, "hunter": 2}
CHANCE = {"passive": 0.0, "territorial": 0.30, "hunter": 0.45}

WANDER_CHANCE = 0.25        # шанс, что бродячая тварь сдвинется за шаг игрока
WANDER_SETTING = "mob_wander"
HUNT_SETTING = "mob_hunt"


def of(mob_index):
    """Характер твари. У старых записей поля нет — считаем пассивной."""
    try:
        row = data.MOBS[int(mob_index)]
    except (IndexError, ValueError, TypeError):
        return data.DEFAULT_BEHAVIOR
    kind = row[9] if len(row) > 9 else data.DEFAULT_BEHAVIOR
    return kind if kind in data.BEHAVIORS else data.DEFAULT_BEHAVIOR


def label(mob_index):
    icon, name, _hint = data.BEHAVIORS[of(mob_index)]
    return f"{icon} {name}"


def enabled(store, key, default=True):
    return bool(store.settings.get(key, default))


# ── охота: тварь идёт на игрока сама ────────────────────────

def hunters_near(store, p, rng=None):
    """Тварь, решившая напасть на игрока. Индекс моба или None.

    Смотрим клетки вокруг игрока: чем ближе тварь и злее её нрав, тем выше
    шанс. Напавшая уходит со своей клетки — она теперь в бою.
    """
    if p.combat or not enabled(store, HUNT_SETTING):
        return None
    here = store.world.get(f"{p.loc}:{p.x}:{p.y}")
    if here is not None and here.mob >= 0:
        return None                      # на клетке и так есть кого бить
    rng = rng or random

    # В катаклизм твари смелее: общий шанс идёт бонусом к характеру.
    boost = cataclysm.effects(store, p.loc).get("ambush", 0.0) * 0.5

    candidates = []
    for dx in (-2, -1, 0, 1, 2):
        for dy in (-2, -1, 0, 1, 2):
            if dx == 0 and dy == 0:
                continue
            dist = max(abs(dx), abs(dy))
            c = W.cell_at(store.world, p.loc, p.x + dx, p.y + dy, getattr(p, "floor", 0))
            if c is None or c.mob < 0:
                continue
            kind = of(c.mob)
            if dist > REACH.get(kind, 0):
                continue
            chance = CHANCE.get(kind, 0.0) + boost
            if dist > 1:
                chance *= 0.6            # издалека решаются реже
            candidates.append((c, chance))

    if not candidates:
        return None
    rng.shuffle(candidates)
    for c, chance in candidates:
        if rng.random() < chance:
            mob_index = c.mob
            c.mob = -1
            # Ключ домашней клетки отдаём вместе с тварью: бой должен
            # знать, куда её вернуть при побеге и где её воскрешать.
            return mob_index, c.key
    return None


# ── бродяжничество ──────────────────────────────────────────

def wander(store, loc, rng=None):
    """Двигает бродячих тварей по локации. Возвращает число сдвигов.

    Ходят только `hunter`: у остальных нрав сидячий. Тварь не заходит на
    клетку игрока, в переходы и на спавн — иначе она бы «телепортировала»
    игрока в бой без его хода.
    """
    if not enabled(store, WANDER_SETTING):
        return 0
    rng = rng or random
    busy = {f"{q.loc}:{q.x}:{q.y}" for q in store.players.values()}
    moved = 0
    movers = [c for c in store.world.values()
              if c.loc == loc and c.mob >= 0 and of(c.mob) == "hunter"]
    rng.shuffle(movers)
    for c in movers:
        if rng.random() >= WANDER_CHANCE:
            continue
        spots = []
        for dx, dy in W.DIRS.values():
            n = W.cell_at(store.world, loc, c.x + dx, c.y + dy)
            if (n is not None and n.passable and n.mob < 0 and n.npc < 0
                    and not n.link and n.key not in busy
                    and (n.x, n.y) != W.SPAWN):
                spots.append(n)
        if not spots:
            continue
        target = rng.choice(spots)
        target.mob, c.mob = c.mob, -1
        # Метку респавна тащим за тварью: иначе исходная клетка «родит» ещё одну.
        target.mob_at, c.mob_at = c.mob_at, 0.0
        moved += 1
    return moved


def tick(store, p, rng=None):
    """Шаг жизни тварей вокруг игрока: сначала брожение, затем охота."""
    wander(store, p.loc, rng)
    return hunters_near(store, p, rng)


# ── сводка для панели ───────────────────────────────────────

def census(store, loc=None):
    """Сколько тварей какого нрава сейчас в мире."""
    out = {k: 0 for k in data.BEHAVIORS}
    for c in store.world.values():
        if c.mob >= 0 and (loc is None or c.loc == int(loc)):
            out[of(c.mob)] = out.get(of(c.mob), 0) + 1
    return out
