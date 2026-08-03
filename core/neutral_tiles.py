"""Нейтральные фоны клеток перемещения с видом сверху.

Фоны не хранятся в каждой строке БД: тип тайла и соседние дороги определяют
картинку автоматически. Это позволяет менять формы дорог кистью в админке,
а бот сам подставляет прямой участок, поворот, Т-образный или полный
перекрёсток под прозрачный слой Pillow.
"""

TILE_BACKGROUNDS = {
    "grass": "/static/tiles/meadow.png",
    "forest": "/static/tiles/forest_canopy.png",
    "desert": "/static/tiles/desert_track.png",
    "swamp": "/static/tiles/swamp.png",
    "water": "/static/tiles/water_shore.png",
    "cave": "/static/tiles/cave_floor.png",
}

# Базовые дорожные арты: straight — север↔юг; turn — юг↔восток;
# T — юг↔запад↔восток. Нужную сторону получаем поворотом Pillow.
ROAD_STRAIGHT = "/static/tiles/road_straight.png"
ROAD_TURN = "/static/tiles/road_turn.png"
ROAD_T = "/static/tiles/road_t.png"
ROAD_CROSS = "/static/tiles/road_cross.png"

_CARDINALS = {
    "n": (-1, 0), "e": (0, 1), "s": (1, 0), "w": (0, -1),
}


def _road_sides(cell, cells) -> set[str]:
    """Стороны, по которым дорожная клетка соединена с соседями."""
    by_pos = {(int(c.x), int(c.y)): c for c in cells}
    sides = set()
    for side, (dx, dy) in _CARDINALS.items():
        neighbor = by_pos.get((int(cell.x) + dx, int(cell.y) + dy))
        if neighbor and neighbor.is_passable and neighbor.tile_type == "road":
            sides.add(side)
    return sides


def road_background(cell, cells) -> tuple[str, int]:
    """URL и угол (clockwise) дорожного фона по её соседям."""
    sides = _road_sides(cell, cells)
    if len(sides) >= 4:
        return ROAD_CROSS, 0
    if len(sides) == 3:
        # Базовый T не имеет выхода на север.
        missing = ({"n", "e", "s", "w"} - sides).pop()
        return ROAD_T, {"n": 0, "e": 90, "s": 180, "w": 270}[missing]
    if len(sides) == 2:
        if sides in ({"n", "s"}, {"e", "w"}):
            return ROAD_STRAIGHT, 0 if sides == {"n", "s"} else 90
        # Поворот базы: юг → восток.
        turns = {
            frozenset(("s", "e")): 0,
            frozenset(("s", "w")): 90,
            frozenset(("n", "w")): 180,
            frozenset(("n", "e")): 270,
        }
        return ROAD_TURN, turns[frozenset(sides)]
    if sides and sides <= {"e", "w"}:
        return ROAD_STRAIGHT, 90
    return ROAD_STRAIGHT, 0


def background_for(cell, cells) -> tuple[str, int] | None:
    """Вернуть подходящий нейтральный фон клетки или ``None``.

    Клетка с собственным ``image_url`` обрабатывается вызывающим кодом раньше
    и не попадает сюда: ручной фон администратора всегда важнее автоматики.
    """
    tile_type = (getattr(cell, "tile_type", "") or "").lower()
    if tile_type == "road":
        return road_background(cell, cells)
    url = TILE_BACKGROUNDS.get(tile_type)
    return (url, 0) if url else None
