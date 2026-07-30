"""Характеры тварей и орда для серверного стека.

Паритет с `engine/behavior.py` и `engine/horde.py`: значения нравов,
дальность и шансы берутся оттуда же.

  passive     — ждёт на месте;
  territorial — бросается на подошедшего вплотную;
  hunter      — бродит и сам идёт на игрока за две клетки.

Во время катаклизма шансы растут, а тварей становится вдвое больше —
в серверном стеке популяцией заведует `core/spawns.py`, поэтому здесь
только множитель и решение «нападать ли».
"""
import random

from sqlalchemy import select

from engine import behavior as E
from engine import data as engine_data
from engine.cataclysm_kinds import MOB_MULT  # noqa: F401
from core.models import Cell, Mob

BEHAVIORS = engine_data.BEHAVIORS
REACH = E.REACH
CHANCE = E.CHANCE
WANDER_CHANCE = E.WANDER_CHANCE
DEFAULT = "passive"


def of(mob) -> str:
    """Характер твари. У старых записей поля нет — считаем пассивной."""
    kind = getattr(mob, "behavior", None) or DEFAULT
    return kind if kind in BEHAVIORS else DEFAULT


def label(mob) -> str:
    icon, name, _hint = BEHAVIORS[of(mob)]
    return f"{icon} {name}"


async def hunter_near(session, character, boost=0.0, rng=None):
    """Тварь, решившая напасть сама. Возвращает клетку с ней или None.

    Смотрим клетки вокруг героя: чем ближе тварь и злее нрав, тем выше
    шанс. Пассивные не нападают никогда — как и в браузерном стеке.
    """
    rng = rng or random
    result = await session.execute(
        select(Cell).where(Cell.location_id == character.location_id)
                    .where(Cell.floor == (character.floor or 0))
                    .where(Cell.mob_id.isnot(None))
    )
    cells = result.scalars().all()
    if not cells:
        return None

    here = await session.get(Cell, character.cell_id) if character.cell_id else None
    if here is None:
        return None
    if here.mob_id:
        return None                       # на клетке и так есть кого бить

    candidates = []
    for c in cells:
        dist = max(abs(c.x - here.x), abs(c.y - here.y))
        if dist == 0 or dist > 2:
            continue
        mob = await session.get(Mob, c.mob_id)
        if mob is None:
            continue
        kind = of(mob)
        if dist > REACH.get(kind, 0):
            continue
        chance = CHANCE.get(kind, 0.0) + boost
        if dist > 1:
            chance *= 0.6
        candidates.append((c, chance))

    rng.shuffle(candidates)
    for c, chance in candidates:
        if rng.random() < chance:
            return c
    return None


async def wander(session, location_id, floor=0, rng=None):
    """Двигает бродячих тварей. Возвращает число сдвигов.

    Ходят только охотники: у остальных нрав сидячий.
    """
    rng = rng or random
    result = await session.execute(
        select(Cell).where(Cell.location_id == location_id)
                    .where(Cell.floor == floor)
    )
    cells = result.scalars().all()
    by_pos = {(c.x, c.y): c for c in cells}
    moved = 0

    movers = []
    for c in cells:
        if not c.mob_id:
            continue
        mob = await session.get(Mob, c.mob_id)
        if mob is not None and of(mob) == "hunter":
            movers.append(c)
    rng.shuffle(movers)

    for c in movers:
        if rng.random() >= WANDER_CHANCE:
            continue
        spots = []
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            n = by_pos.get((c.x + dx, c.y + dy))
            if (n is not None and n.is_passable and not n.mob_id
                    and not n.has_npc and n.target_location_id is None):
                spots.append(n)
        if not spots:
            continue
        target = rng.choice(spots)
        target.mob_id, c.mob_id = c.mob_id, None
        moved += 1
    if moved:
        await session.flush()
    return moved


def census(mobs) -> dict:
    """Сколько тварей какого нрава — для админки."""
    out = {k: 0 for k in BEHAVIORS}
    for m in mobs:
        out[of(m)] = out.get(of(m), 0) + 1
    return out
