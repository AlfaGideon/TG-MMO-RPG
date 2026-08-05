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
    "jungle": "/static/tiles/jungle.png",
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


def get_time_suffix():
    """Возвращает суффикс времени суток на основе системного времени."""
    import datetime
    hour = datetime.datetime.now().hour
    if 6 <= hour < 18:
        return "_day"
    return "_night"

def get_season_suffix():
    """Возвращает суффикс сезона на основе месяца."""
    import datetime
    month = datetime.datetime.now().month
    if month in (12, 1, 2):
        return "_winter"
    return ""

def background_for(cell, cells) -> tuple[str, int] | None:
    """Вернуть подходящий нейтральный фон клетки или ``None``.

    Клетка с собственным ``image_url`` обрабатывается вызывающим кодом раньше
    и не попадает сюда: ручной фон администратора всегда важнее автоматики.
    """
    tile_type = (getattr(cell, "tile_type", "") or "").lower()
    time_sfx = get_time_suffix()
    season_sfx = get_season_suffix()
    
    # Приоритет: именной файл -> зима -> день/ночь -> дефолт
    def get_variant(base_path):
        from core.assets import local_asset_exists
        import hashlib
        ext = ".png"
        p_base = base_path.replace(ext, "")
        
        # 1. Проверяем именной файл (хэш названия)
        name = getattr(cell, 'name', '')
        if name:
            name_hash = hashlib.md5(name.encode()).hexdigest()[:8]
            named_url = f"/static/tiles/named/{name_hash}{time_sfx}{ext}"
            if local_asset_exists(named_url):
                return named_url, 0

        prefix = season_sfx if season_sfx == "_winter" else time_sfx
        
        candidates = []
        # Проверяем наличие пронумерованных вариантов (до 10 штук)
        for v in range(1, 11):
            v_url = f"{p_base}{prefix}_{v}{ext}"
            if local_asset_exists(v_url):
                candidates.append(v_url)
        
        if not candidates:
            sfx_url = f"{p_base}{prefix}{ext}"
            if local_asset_exists(sfx_url):
                candidates.append(sfx_url)
        
        if not candidates:
            candidates.append(base_path)
            
        # Используем хэш от названия клетки + ID, чтобы выбор был стабильным,
        # но зависел от контента клетки (названия).
        seed_str = f"{getattr(cell, 'name', '')}_{getattr(cell, 'id', 0)}"
        seed_hash = int(hashlib.md5(seed_str.encode()).hexdigest(), 16)
        idx = seed_hash % len(candidates)
        return candidates[idx], 0

    if tile_type == "road":
        bg, rot = road_background(cell, cells)
        return get_variant(bg)
        
    url = TILE_BACKGROUNDS.get(tile_type)
    if url:
        return get_variant(url)
        
    return None
