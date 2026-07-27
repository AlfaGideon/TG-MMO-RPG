import os
from PIL import Image, ImageDraw, ImageFont

TILE_SIZE = 512
MINIMAP_CELL = 22
MINIMAP_PADDING = 12


def _dark_gradient(size: int) -> Image.Image:
    """Create a dark gradient background when no cell image exists."""
    img = Image.new("RGB", (size, size), (15, 20, 25))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        color = int(15 + (y / size) * 15)
        draw.line([(0, y), (size, y)], fill=(color, color + 5, color + 10))
    return img


def _load_cell_bg(image_url: str | None) -> Image.Image:
    """Load cell background image or return dark gradient."""
    if image_url and os.path.exists(image_url):
        try:
            img = Image.open(image_url).convert("RGB")
            return img.resize((TILE_SIZE, TILE_SIZE), Image.LANCZOS)
        except Exception:
            pass
    return _dark_gradient(TILE_SIZE)


def _draw_minimap(draw: ImageDraw.Draw, cells, player_x: int, player_y: int, offset_x: int, offset_y: int):
    size = 10
    cell_size = MINIMAP_CELL
    bg_w = size * cell_size + 6
    bg_h = size * cell_size + 6

    draw.rectangle([offset_x, offset_y, offset_x + bg_w, offset_y + bg_h],
                   fill=(10, 10, 15), outline=(180, 160, 100), width=2)

    for cy in range(size):
        for cx in range(size):
            cell = next((c for c in cells if c.x == cx and c.y == cy), None)
            px = offset_x + 3 + cx * cell_size
            py = offset_y + 3 + cy * cell_size

            if cx == player_x and cy == player_y:
                color = (0, 255, 100)  # Player - bright green
            elif cell is None or not cell.is_passable:
                color = (25, 25, 30)  # Wall - almost black
            elif cell.mob_id:
                color = (220, 50, 50)  # Enemy - red
            elif cell.has_npc:
                color = (255, 200, 50)  # NPC - gold
            elif cell.has_chest:
                color = (150, 50, 220)  # Chest - purple
            else:
                t = cell.tile_type or "grass"
                color_map = {
                    "grass": (40, 90, 40),
                    "forest": (20, 60, 20),
                    "water": (30, 50, 90),
                    "road": (70, 60, 40),
                    "village": (80, 70, 40),
                    "cave": (40, 35, 50),
                    "wall": (25, 25, 30),
                }
                color = color_map.get(t, (40, 90, 40))

            draw.rectangle([px, py, px + cell_size - 2, py + cell_size - 2], fill=color)


def render_cell_image(cell, cells, player_x: int, player_y: int, output_path: str) -> str:
    # Load background: cell image or dark gradient
    local_path = None
    if cell.image_url:
        # Try local path first
        if cell.image_url.startswith("/static/"):
            local_path = "admin" + cell.image_url
        elif os.path.exists(cell.image_url):
            local_path = cell.image_url

    if local_path and os.path.exists(local_path):
        img = Image.open(local_path).convert("RGB").resize((TILE_SIZE, TILE_SIZE), Image.LANCZOS)
    else:
        img = _dark_gradient(TILE_SIZE)

    draw = ImageDraw.Draw(img)

    # Minimap in top-right corner
    mm_x = TILE_SIZE - (10 * MINIMAP_CELL + 8) - MINIMAP_PADDING
    mm_y = MINIMAP_PADDING
    _draw_minimap(draw, cells, player_x, player_y, mm_x, mm_y)

    # Fonts
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except:
        font = ImageFont.load_default()
        small_font = font

    # Cell name at top-left
    draw.text((MINIMAP_PADDING, MINIMAP_PADDING), cell.name,
              fill=(255, 255, 255), font=font, stroke_width=2, stroke_fill=(0, 0, 0))

    # Coordinates at bottom-left
    coord_text = f"[{cell.x},{cell.y}]"
    draw.text((MINIMAP_PADDING, TILE_SIZE - 32), coord_text,
              fill=(255, 255, 255), font=font, stroke_width=2, stroke_fill=(0, 0, 0))

    # Legend below minimap
    legend_y = mm_y + 10 * MINIMAP_CELL + 12
    legends = [
        ("Ты", (0, 255, 100)),
        ("Враг", (220, 50, 50)),
        ("NPC", (255, 200, 50)),
        ("Сундук", (150, 50, 220)),
    ]
    for i, (text, color) in enumerate(legends):
        ly = legend_y + i * 18
        draw.rectangle([mm_x, ly, mm_x + 12, ly + 12], fill=color)
        draw.text((mm_x + 16, ly - 1), text, fill=(255, 255, 255), font=small_font)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "JPEG", quality=92)
    return output_path


def get_cell_image_path(cell_id: int) -> str:
    return f"data/cell_images/{cell_id}.jpg"


def ensure_cell_image(cell, cells, player_x: int, player_y: int) -> str:
    path = get_cell_image_path(cell.id)
    if os.path.exists(path):
        return path
    return render_cell_image(cell, cells, player_x, player_y, path)
