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


def _dark_bg(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), (18, 22, 28))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        c = int(18 + (y / size) * 8)
        draw.line([(0, y), (size, y)], fill=(c, c + 2, c + 5))
    return img


def _load_bg(image_url: str | None) -> Image.Image:
    if image_url:
        local = None
        if image_url.startswith("/static/"):
            local = "admin" + image_url
        elif os.path.exists(image_url):
            local = image_url
        if local and os.path.exists(local):
            try:
                return Image.open(local).convert("RGB").resize((TILE_SIZE, TILE_SIZE), Image.LANCZOS)
            except Exception:
                pass
    return _dark_bg(TILE_SIZE)


def _draw_minimap(draw: ImageDraw.Draw, cells, player_x: int, player_y: int, ox: int, oy: int):
    """Draw minimap. x=vertical (north-south), y=horizontal (west-east)."""
    size = 10
    cs = MINIMAP_CELL
    bw = size * cs + 4
    bh = size * cs + 4

    draw.rectangle([ox - 2, oy - 2, ox + bw + 2, oy + bh + 2],
                   fill=(30, 30, 35), outline=(100, 100, 110), width=2)

    for row in range(size):      # row = x (0=top/north, 9=bottom/south)
        for col in range(size):  # col = y (0=left/west, 9=right/east)
            cell = next((c for c in cells if c.x == row and c.y == col), None)
            px = ox + col * cs   # y goes horizontally
            py = oy + row * cs   # x goes vertically

            if row == player_x and col == player_y:
                color = (220, 220, 220)  # Player - white
            elif cell is None or not cell.is_passable:
                color = (15, 15, 20)     # Wall
            else:
                color = (60, 65, 70)     # Passable - single color

            draw.rectangle([px, py, px + cs - 2, py + cs - 2], fill=color)


def render_cell_image(cell, cells, player_x: int, player_y: int, output_path: str) -> str:
    img = _load_bg(cell.image_url)
    draw = ImageDraw.Draw(img)

    mm_size = 10 * MINIMAP_CELL
    mm_x = (TILE_SIZE - mm_size) // 2
    mm_y = (TILE_SIZE - mm_size) // 2 - 20
    _draw_minimap(draw, cells, player_x, player_y, mm_x, mm_y)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
    except:
        font = ImageFont.load_default()

    draw.text((20, 12), cell.name, fill=(255, 255, 255),
              font=font, stroke_width=2, stroke_fill=(0, 0, 0))
    draw.text((20, TILE_SIZE - 28), f"[{cell.x},{cell.y}]", fill=(180, 180, 180),
              font=font, stroke_width=2, stroke_fill=(0, 0, 0))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "JPEG", quality=90)
    return output_path


def get_cell_image_path(cell_id: int) -> str:
    return f"data/cell_images/{cell_id}.jpg"


def ensure_cell_image(cell, cells, player_x: int, player_y: int) -> str:
    path = get_cell_image_path(cell.id)
    if os.path.exists(path):
        return path
    return render_cell_image(cell, cells, player_x, player_y, path)


def render_player_map(cells, visited: set, player_x: int, player_y: int, grid_size: int,
                       output_path: str, cell_px: int = 32) -> str:
    """
    Renders a top-down grid map identical in style to the admin panel's cell grid
    (same flat colors per tile type), but only shows cells the player has already
    visited — everything else stays covered in fog-of-war. No borders, no text,
    the image is a tight fit around the grid. The player's current position is
    marked with a single dot; nothing else is drawn on top.

    cells: iterable of objects with .x, .y, .tile_type, .is_passable
    visited: set of (x, y) tuples the character has visited in this location/floor
    """
    size = grid_size * cell_px
    img = Image.new("RGB", (size, size), FOG_COLOR)
    draw = ImageDraw.Draw(img)

    cells_by_pos = {(c.x, c.y): c for c in cells}

    for (x, y) in visited:
        cell = cells_by_pos.get((x, y))
        if cell is None:
            continue
        color = TILE_COLORS.get(cell.tile_type, TILE_COLORS["grass"])
        if not cell.is_passable:
            color = TILE_COLORS["wall"]
        px, py = y * cell_px, x * cell_px
        draw.rectangle([px, py, px + cell_px - 1, py + cell_px - 1], fill=color)

    # Player marker — a simple dot, no text/labels, drawn last so it's always visible
    if (player_x, player_y) in visited or True:
        cx = player_y * cell_px + cell_px // 2
        cy = player_x * cell_px + cell_px // 2
        r = max(3, cell_px // 4)
        draw.ellipse([cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2], fill=PLAYER_RING)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=PLAYER_COLOR)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    img.save(output_path, "PNG")
    return output_path


def get_player_map_path(character_id: int, location_id: int, floor: int) -> str:
    return f"data/player_maps/{character_id}_{location_id}_{floor}.png"
