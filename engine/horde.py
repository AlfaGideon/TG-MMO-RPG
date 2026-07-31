"""Орда и агрессия тварей во время катаклизма.

Пока бушует бедствие, тварей вдвое больше обычного и они не ждут, пока на
них наступят: бросаются из соседних клеток и сбегаются на шум боя. Когда
беда стихает, популяция сама возвращается к мирной норме.

Прибавка помечается в `settings['cataclysm_horde']` — по этому списку
видно, кто «лишний», поэтому удвоение считается от мирной базы и не
накапливается, сколько бы бедствий ни наложилось.
"""
import random

from engine import cataclysm, data
from engine import world as W


def _horde(store):
    lst = store.settings.get(cataclysm.HORDE)
    if not isinstance(lst, list):
        lst = []
        store.settings[cataclysm.HORDE] = lst
    return lst


def rebalance(store, rng=None):
    """Привести число тварей к норме: ×MOB_MULT в беде, обычное в покое.

    Идемпотентна и считает от «мирной» базы (клетки вне орды), поэтому
    два наложившихся бедствия не дают четырёхкратную ораву, а конец одного
    из них не обнуляет прибавку от второго. Возвращает (добавлено, убрано).
    """
    rng = rng or random.Random()
    horde = set(_horde(store))
    added = removed = 0
    by_loc = {}
    for c in store.world.values():
        by_loc.setdefault(c.loc, []).append(c)

    busy = {f"{p.loc}:{p.x}:{p.y}" for p in store.players.values()}
    for loc, cells in by_loc.items():
        # Мирная база — твари, которых орда не приводила.
        base = sum(1 for c in cells if c.mob >= 0 and c.key not in horde)
        mine = [c for c in cells if c.key in horde]
        alive = sum(1 for c in mine if c.mob >= 0)
        target = int(base * cataclysm.MOB_MULT) if cataclysm.raging(store, loc) else base
        need = target - base - alive

        if need > 0:
            free = [c for c in cells
                    if c.mob < 0 and c.passable and not c.link and c.npc < 0
                    and c.key not in horde and c.key not in busy
                    and (c.x, c.y) != W.SPAWN]
            rng.shuffle(free)
            for c in free[:need]:
                c.mob = _pick_mob(loc, rng)
                horde.add(c.key)
                added += 1
        elif need < 0:
            # Снимаем только живых: убитые уже не в счёт, иначе они «съедали»
            # квоту и часть орды переживала конец бедствия.
            for c in [c for c in mine if c.mob >= 0][:-need]:
                c.mob = -1
                removed += 1
                horde.discard(c.key)

        # Убитых из орды забываем — они уже не наши.
        for c in mine:
            if c.mob < 0:
                horde.discard(c.key)

    store.settings[cataclysm.HORDE] = sorted(horde)
    return added, removed


def _pick_mob(loc, rng):
    """Тварь под стать локации: свои, иначе любая по уровню локации."""
    own = [i for i, m in enumerate(data.MOBS) if m[8] == loc]
    if own:
        return rng.choice(own)
    lvl = data.LOCATIONS[loc][3] if loc < len(data.LOCATIONS) else 1
    fit = [i for i, m in enumerate(data.MOBS) if m[2] <= max(1, lvl) + 2]
    return rng.choice(fit or range(len(data.MOBS)))


def prowl(store, p, rng=None):
    """Тварь с соседней клетки бросается на игрока сама. Индекс моба или None.

    Работает только в катаклизм: в мирное время шанс `ambush` равен нулю и
    твари смирно ждут, пока на них наступят. Напавшая тварь уходит со своей
    клетки — она теперь в бою, а не поджидает там же.
    """
    if p.combat or not cataclysm.raging(store, p.loc):
        return None
    chance = cataclysm.effects(store, p.loc).get("ambush", 0.0)
    if chance <= 0:
        return None
    rng = rng or random
    if rng.random() >= chance:
        return None
    here = store.world.get(f"{p.loc}:{p.x}:{p.y}")
    if here is not None and here.mob >= 0:
        return None                      # на клетке и так есть кого бить
    near = []
    for dx, dy in W.DIRS.values():
        c = W.cell_at(store.world, p.loc, p.x + dx, p.y + dy, getattr(p, "floor", 0))
        if c is not None and c.mob >= 0:
            near.append(c)
    if not near:
        return None
    c = rng.choice(near)
    mob_index = c.mob
    c.mob = -1
    # Ключ домашней клетки — чтобы боевая система вернула/воскресила тварь
    # там, где она стояла, а не под игроком.
    return mob_index, c.key
