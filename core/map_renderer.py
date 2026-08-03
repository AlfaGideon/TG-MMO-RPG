import os
from PIL import Image, ImageDraw, ImageFont

TILE_SIZE = 512
MINIMAP_CELL = 36

# Same palette as the admin panel's cell grid (admin/templates/editor_location.html)
TILE_COLORS = {
    "wall": (42, 42, 53),
    "grass": (26, 58, 26),
    "forest": (13, 43, 13),
    "water": (10, 26, 58),
    "road": (58, 42, 26),
    "village": (58, 42, 13),
    "cave": (26, 26, 42),
    "portal": (61, 26, 92),
}
FOG_COLOR = (15, 15, 19)       # unvisited / fog of war — matches --bg-dark
PLAYER_COLOR = (220, 220, 220)
PLAYER_RING = (139, 92, 246)   # --accent

# Pillow's built-in bitmap font does not contain Cyrillic. In slim Docker
# images that means Russian labels are rendered as empty boxes/crosses.
# Keep a wide list of common Cyrillic-capable fonts and install DejaVu in
# Dockerfiles; TG_MMO_FONT_PATH can override this in custom deployments.
_FONT_PATHS = (
    os.getenv("TG_MMO_FONT_PATH", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
)


def _dark_bg(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), (18, 22, 28))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        c = int(18 + (y / size) * 8)
        draw.line([(0, y), (size, y)], fill=(c, c + 2, c + 5))
    return img


def _load_bg(image_url: str | None) -> Image.Image:
    if image_url:
        from core.assets import local_asset_path
        local = local_asset_path(image_url)
        if local and local.is_file():
            try:
                return Image.open(local).convert("RGB").resize(
                    (TILE_SIZE, TILE_SIZE), Image.LANCZOS)
            except Exception:
                pass
    return _dark_bg(TILE_SIZE)


def _grid_size_from_cells(cells, default: int = 10) -> int:
    """Infer square grid size from cells; works for 10×10 and 25×25 castles."""
    coords = [max(int(getattr(c, "x", 0)), int(getattr(c, "y", 0))) for c in cells]
    return max(default, (max(coords) + 1) if coords else default)


def _draw_minimap(draw: ImageDraw.Draw, cells, player_x: int, player_y: int,
                  ox: int, oy: int, grid_size: int | None = None,
                  cell_px: int | None = None):
    """Draw minimap. x=vertical (north-south), y=horizontal (west-east).

    The old minimap was hard-coded to 10×10. Corner castles and their
    underground floors are 25×25, so coordinates like [12,12] or [19,5]
    were outside the drawn area and the player marker disappeared.
    """
    cells = list(cells)
    size = max(1, int(grid_size or _grid_size_from_cells(cells)))
    cs = max(6, int(cell_px or min(MINIMAP_CELL, 360 // size)))
    bw = size * cs + 4
    bh = size * cs + 4
    by_pos = {(int(c.x), int(c.y)): c for c in cells}

    draw.rectangle([ox - 2, oy - 2, ox + bw + 2, oy + bh + 2],
                   fill=(30, 30, 35), outline=(100, 100, 110), width=2)

    gap = 1 if cs <= 10 else 2
    for row in range(size):      # row = x (0=top/north)
        for col in range(size):  # col = y (0=left/west)
            cell = by_pos.get((row, col))
            px = ox + col * cs   # y goes horizontally
            py = oy + row * cs   # x goes vertically

            if row == player_x and col == player_y:
                color = (220, 220, 220)  # Player - white
            elif cell is None or not cell.is_passable:
                color = (15, 15, 20)     # Wall / outside
            else:
                color = (60, 65, 70)     # Passable - single color

            draw.rectangle([px, py, px + cs - gap, py + cs - gap], fill=color)

    # Extra ring so the marker remains visible when a cell is small (25×25).
    if 0 <= player_x < size and 0 <= player_y < size:
        cx = ox + player_y * cs + cs // 2
        cy = oy + player_x * cs + cs // 2
        r = max(3, cs // 3)
        draw.ellipse([cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1],
                     outline=PLAYER_RING, width=max(1, cs // 5))


def render_cell_image(cell, cells, player_x: int, player_y: int, output_path: str) -> str:
    cells = list(cells)
    img = _load_bg(cell.image_url)
    draw = ImageDraw.Draw(img)

    grid_size = _grid_size_from_cells(cells)
    mm_cell = max(6, min(MINIMAP_CELL, 360 // max(1, grid_size)))
    mm_size = grid_size * mm_cell
    mm_x = (TILE_SIZE - mm_size) // 2
    mm_y = (TILE_SIZE - mm_size) // 2 - 20
    _draw_minimap(draw, cells, player_x, player_y, mm_x, mm_y,
                  grid_size=grid_size, cell_px=mm_cell)

    font = _fit_font(18)

    draw.text((20, 12), cell.name, fill=(255, 255, 255),
              font=font, stroke_width=2, stroke_fill=(0, 0, 0))
    draw.text((20, TILE_SIZE - 28), f"[{cell.x},{cell.y}]", fill=(180, 180, 180),
              font=font, stroke_width=2, stroke_fill=(0, 0, 0))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "JPEG", quality=90)
    return output_path


def get_cell_image_path(cell_id: int) -> str:
    # v2 invalidates old cached JPEGs that were rendered with a 10×10-only
    # minimap and, on slim images, a non-Cyrillic Pillow fallback font.
    return f"data/cell_images/v2/{cell_id}.jpg"


def ensure_cell_image(cell, cells, player_x: int, player_y: int) -> str:
    path = get_cell_image_path(cell.id)
    if os.path.exists(path):
        return path
    return render_cell_image(cell, cells, player_x, player_y, path)


def render_dungeon_map(cells, player_x: int, player_y: int, grid_size: int,
                       output_path: str, cell_px: int = 20) -> str:
    """Карта подземелья: только посещённые клетки, стены, сундуки, выход.

    Раньше в подземельях карты не было вообще — игрок бродил вслепую.
    """
    size = grid_size * cell_px
    img = Image.new("RGB", (size, size), FOG_COLOR)
    draw = ImageDraw.Draw(img)

    for c in cells:
        if not getattr(c, "is_visited", False):
            continue
        px, py = c.y * cell_px, c.x * cell_px
        if not c.is_passable:
            color = TILE_COLORS["wall"]
        elif getattr(c, "has_exit", False):
            color = (61, 26, 92)          # лестница вниз — фиолетовый
        elif getattr(c, "has_chest", False):
            color = (120, 90, 30)         # сундук — золотистый
        elif getattr(c, "has_mob", False):
            color = (110, 35, 35)         # монстр — красный
        else:
            color = TILE_COLORS.get(c.tile_type, TILE_COLORS["cave"])
        draw.rectangle([px, py, px + cell_px - 1, py + cell_px - 1], fill=color)

    cx = player_y * cell_px + cell_px // 2
    cy = player_x * cell_px + cell_px // 2
    r = max(3, cell_px // 4)
    draw.ellipse([cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2], fill=PLAYER_RING)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=PLAYER_COLOR)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    img.save(output_path, "PNG")
    return output_path


def get_dungeon_map_path(run_id: int, floor: int) -> str:
    return f"data/dungeon_maps/{run_id}_{floor}.png"


# Уровни масштаба карты: 0 — самый близкий вид вокруг героя,
# ZOOM_LEVELS-1 — вся локация целиком. Кнопки +/- на экранах карты и
# перемещения двигаются по этим уровням.
ZOOM_LEVELS = 3
_ZOOM_FRACTIONS = (0.25, 0.45)  # доля сетки для радиуса окна (уровни 0..N-2)
DEFAULT_ZOOM = ZOOM_LEVELS - 1  # вся локация — одинаково на карте и в пути


def zoom_radius_for(grid_size: int, zoom: int):
    """Радиус окна вокруг героя (в клетках) для уровня масштаба.

    Максимальный уровень — вся локация (None). Минимальный — окно
    ~четверть сетки, но не меньше 2 клеток вокруг героя.
    """
    zoom = max(0, min(int(zoom), ZOOM_LEVELS - 1))
    if zoom >= ZOOM_LEVELS - 1:
        return None
    return max(2, min(grid_size - 1, round(grid_size * _ZOOM_FRACTIONS[zoom])))


def render_player_map(cells, visited: set, player_x: int, player_y: int, grid_size: int,
                       output_path: str, cell_px: int | None = None,
                       zoom_radius: int | None = None) -> str:
    """
    Renders a top-down grid map identical in style to the admin panel's cell grid
    (same flat colors per tile type), but only shows cells the player has already
    visited — everything else stays covered in fog-of-war. No borders, no text,
    the image is a tight fit around the grid. The player's current position is
    marked with a single dot; nothing else is drawn on top.

    cells: iterable of objects with .x, .y, .tile_type, .is_passable
    visited: set of (x, y) tuples the character has visited in this location/floor
    zoom_radius: None — вся локация; число — окно (2r+1)×(2r+1) вокруг героя,
                 скользящее по краям сетки (приближение кнопкой «➕»).
    Клетка масштабируется автоматически, чтобы картинка была ~720 px
    на любой локации (10×10 и замки 25×25 выглядят одинаково крупно).
    """
    grid_size = max(1, int(grid_size))
    if zoom_radius is None:
        x0 = y0 = 0
        view = grid_size
    else:
        r = max(1, int(zoom_radius))
        view = min(grid_size, 2 * r + 1)
        x0 = max(0, min(player_x - r, grid_size - view))
        y0 = max(0, min(player_y - r, grid_size - view))
    x1, y1 = x0 + view, y0 + view  # правая/нижняя граница (не включая)

    cell_px = max(8, int(cell_px or max(16, 720 // view)))
    size = view * cell_px
    img = Image.new("RGB", (size, size), FOG_COLOR)
    draw = ImageDraw.Draw(img)

    cells_by_pos = {(c.x, c.y): c for c in cells}

    for (x, y) in visited:
        if not (x0 <= x < x1 and y0 <= y < y1):
            continue
        cell = cells_by_pos.get((x, y))
        if cell is None:
            continue
        color = TILE_COLORS.get(cell.tile_type, TILE_COLORS["grass"])
        if not cell.is_passable:
            color = TILE_COLORS["wall"]
        px, py = (y - y0) * cell_px, (x - x0) * cell_px
        draw.rectangle([px, py, px + cell_px - 1, py + cell_px - 1], fill=color)

    # Player marker — a simple dot, no text/labels, drawn last so it's always visible
    if x0 <= player_x < x1 and y0 <= player_y < y1:
        cx = (player_y - y0) * cell_px + cell_px // 2
        cy = (player_x - x0) * cell_px + cell_px // 2
        r = max(3, cell_px // 4)
        draw.ellipse([cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2], fill=PLAYER_RING)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=PLAYER_COLOR)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    img.save(output_path, "PNG")
    return output_path


def get_player_map_path(character_id: int, location_id: int, floor: int,
                        zoom: int | None = None) -> str:
    suffix = "" if zoom is None else f"_z{zoom}"
    return f"data/player_maps/{character_id}_{location_id}_{floor}{suffix}.png"


# ── Карта мира (сетка локаций) ────────────────────────────

LOC_TYPE_COLORS = {
    "safe": (46, 125, 50),       # зелёный — безопасно
    "dangerous": (150, 90, 30),  # охра — опасно
    "dungeon": (61, 26, 92),     # фиолетовый — подземелье
    "boss": (140, 40, 40),       # красный — логово босса
}
LOC_TYPE_ICONS = {"safe": "🛡", "dangerous": "⚠", "dungeon": "💀", "boss": "👹"}


def _fit_font(size: int):
    for path in _FONT_PATHS:
        if not path or not os.path.exists(path):
            continue
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    # Last resort. This font is ASCII-only in many Pillow builds, so Docker
    # images install DejaVu; returning it here keeps the bot alive if a custom
    # host removed all fonts.
    return ImageFont.load_default()


def _wrap(draw, text: str, font, max_w: int, max_lines: int = 2) -> list:
    """Перенос названия локации по словам под ширину плитки."""
    words = (text or "").split()
    lines, cur = [], ""
    for word in words:
        probe = f"{cur} {word}".strip()
        if draw.textlength(probe, font=font) <= max_w or not cur:
            cur = probe
        else:
            lines.append(cur)
            cur = word
            if len(lines) == max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if not lines:
        return [""]
    # Если не влезло — обрезаем последнюю строку многоточием.
    while draw.textlength(lines[-1], font=font) > max_w and len(lines[-1]) > 1:
        lines[-1] = lines[-1][:-1]
    if len(" ".join(lines)) < len(text or ""):
        lines[-1] = lines[-1].rstrip() + "…"
    return lines


def world_bounds(locations, world_grid_size: int, pad: int = 0):
    """Прямоугольник мировой карты, реально занятый локациями (+рамка).

    Раньше карта всегда рисовалась во всю сетку 10×10, и пять стартовых
    локаций терялись крошечной полоской в море тумана — из-за чего строка
    вдоль оси X выглядела «неправильно повёрнутой». Обрезаем пустоту.
    """
    xs = [l.world_x for l in locations
          if 0 <= l.world_x < world_grid_size and 0 <= l.world_y < world_grid_size]
    ys = [l.world_y for l in locations
          if 0 <= l.world_x < world_grid_size and 0 <= l.world_y < world_grid_size]
    if not xs:
        return 0, 0, min(world_grid_size, 3) - 1, min(world_grid_size, 3) - 1
    x0 = max(0, min(xs) - pad)
    y0 = max(0, min(ys) - pad)
    x1 = min(world_grid_size - 1, max(xs) + pad)
    y1 = min(world_grid_size - 1, max(ys) + pad)
    return x0, y0, x1, y1


def render_world_map(locations, visited_ids: set, current_loc_id: int,
                     world_grid_size: int, output_path: str, cell_px: int = 128) -> str:
    """Мировая карта: сетка локаций с туманом войны по посещённости.

    Ось world_x — горизонталь (запад→восток), world_y — вертикаль
    (север→юг): та же система координат, что в `core/worldgen.DIRS`
    и в сетке админ-панели. Рисуем только занятую часть мира, поэтому
    ряд локаций вдоль X читается как настоящий ряд, а не как полоска
    пикселей в углу пустого поля.
    """
    locations = list(locations)
    x0, y0, x1, y1 = world_bounds(locations, world_grid_size)
    cols, rows = (x1 - x0 + 1), (y1 - y0 + 1)

    # Плитки не должны получаться микроскопическими на широком мире.
    cell_px = max(72, min(cell_px, 1600 // max(cols, rows)))
    width, height = cols * cell_px, rows * cell_px
    img = Image.new("RGB", (width, height), FOG_COLOR)
    draw = ImageDraw.Draw(img)

    name_font = _fit_font(max(11, cell_px // 9))
    icon_font = _fit_font(max(14, cell_px // 5))

    placed = {}
    for loc in locations:
        if not (x0 <= loc.world_x <= x1 and y0 <= loc.world_y <= y1):
            continue
        placed[(loc.world_x, loc.world_y)] = loc

    # Дороги между соседями — мир читается как связная карта, а не как плитки.
    for (wx, wy), loc in placed.items():
        for dx, dy in ((1, 0), (0, 1)):
            nb = placed.get((wx + dx, wy + dy))
            if nb is None:
                continue
            if loc.id not in visited_ids and nb.id not in visited_ids:
                continue
            ax = (wx - x0) * cell_px + cell_px // 2
            ay = (wy - y0) * cell_px + cell_px // 2
            bx = (wx + dx - x0) * cell_px + cell_px // 2
            by = (wy + dy - y0) * cell_px + cell_px // 2
            draw.line([ax, ay, bx, by], fill=(80, 84, 92), width=max(2, cell_px // 24))

    for (wx, wy), loc in placed.items():
        px, py = (wx - x0) * cell_px, (wy - y0) * cell_px
        pad = max(3, cell_px // 16)
        box = [px + pad, py + pad, px + cell_px - pad, py + cell_px - pad]
        if True:  # loc.id in visited_ids: (всегда раскрываем карту, чтобы видеть все 36+ локаций)
            color = LOC_TYPE_COLORS.get(loc.location_type.value, (60, 65, 70))
            draw.rectangle(box, fill=color, outline=(120, 126, 134), width=2)
            lines = _wrap(draw, loc.name, name_font, cell_px - 2 * pad - 6)
            line_h = max(12, cell_px // 8)
            total_h = line_h * len(lines)
            ty = py + cell_px // 2 - total_h // 2 + line_h // 3
            for line in lines:
                tw = draw.textlength(line, font=name_font)
                draw.text((px + cell_px // 2 - tw / 2, ty), line,
                          fill=(240, 240, 240), font=name_font,
                          stroke_width=2, stroke_fill=(0, 0, 0))
                ty += line_h
            lvl = f"ур. {loc.min_level or 1}+"
            lw = draw.textlength(lvl, font=name_font)
            draw.text((px + cell_px // 2 - lw / 2, py + cell_px - pad - line_h - 2),
                      lvl, fill=(215, 215, 215), font=name_font,
                      stroke_width=2, stroke_fill=(0, 0, 0))
            # Тип локации — цветная полоска сверху: emoji в TTF-шрифте
            # Pillow не рисует (выходит пустой прямоугольник).
            draw.rectangle([px + pad, py + pad, px + cell_px - pad,
                            py + pad + max(4, cell_px // 20)],
                           fill=tuple(min(255, c + 60) for c in color))
        else:
            draw.rectangle(box, fill=(28, 30, 36), outline=(55, 58, 66))
            qw = draw.textlength("?", font=icon_font)
            draw.text((px + cell_px // 2 - qw / 2, py + cell_px // 2 - cell_px // 10),
                      "?", fill=(95, 98, 106), font=icon_font)
        if loc.id == current_loc_id:
            draw.rectangle([px + 2, py + 2, px + cell_px - 3, py + cell_px - 3],
                           outline=PLAYER_RING, width=max(3, cell_px // 24))

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    img.save(output_path, "PNG")
    return output_path


def get_world_map_path(character_id: int) -> str:
    return f"data/player_maps/world_{character_id}.png"
