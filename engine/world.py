"""Генерация бесшовного мира: 5 локаций по 10x10 клеток."""
import random
from collections import deque

from engine import data
from engine.models import Cell

SIZE = 10
SPAWN = (5, 5)


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


def generate(seed=1337):
    """Возвращает {"cells": {key: Cell}, "locations": [...]}."""
    rnd = random.Random(seed)
    cells = {}
    story = 0

    for li in range(len(data.LOCATIONS)):
        batch = []
        for x in range(SIZE):
            for y in range(SIZE):
                border = x in (0, SIZE - 1) or y in (0, SIZE - 1)
                wall = border or (rnd.random() < 0.15 and (x, y) != SPAWN)
                name, desc, tile = data.STORIES[story % len(data.STORIES)]
                story += 1
                batch.append(Cell(loc=li, x=x, y=y, name=name, desc=desc,
                                  tile="wall" if wall else tile, passable=not wall))
        _connect(batch)
        for c in batch:
            cells[c.key] = c

    _link_locations(cells)
    _populate(cells, rnd)
    return cells


def _link_locations(cells):
    """Восточная граница локации A ↔ западная граница локации B."""
    for a in range(len(data.LOCATIONS) - 1):
        b = a + 1
        for row in range(1, SIZE - 1):
            ca = cells[f"{a}:{row}:{SIZE - 1}"]
            cb = cells[f"{b}:{row}:0"]
            for c in (ca, cb):
                c.passable = True
                c.tile = "road"
                c.name = "Тракт между землями"
                c.desc = "Утоптанная дорога уходит вдаль."
            ca.link = (b, row, 1)
            cb.link = (a, row, SIZE - 2)


def _populate(cells, rnd):
    """Расставить NPC, мобов и сундуки."""
    free = lambda li: [c for c in cells.values()
                       if c.loc == li and c.passable and not c.link
                       and (c.x, c.y) != SPAWN and c.mob < 0 and c.npc < 0]

    # NPC — только в стартовой безопасной локации
    spots = free(0)
    rnd.shuffle(spots)
    for i in range(min(len(data.NPCS), len(spots))):
        spots[i].npc = i

    # Мобы: по несколько экземпляров каждого вида в своей локации
    for mi, m in enumerate(data.MOBS):
        li = m[8]
        count = 1 if m[0] == "Пожиратель Глубин" else 4
        spots = free(li)
        rnd.shuffle(spots)
        for c in spots[:count]:
            c.mob = mi

    # Сундуки в опасных локациях
    for li in (1, 2, 3, 4):
        spots = free(li)
        rnd.shuffle(spots)
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
