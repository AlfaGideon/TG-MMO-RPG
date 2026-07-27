import os
from PIL import Image, ImageDraw, ImageFont

TILE_SIZE = 512
MINIMAP_CELL = 36
MINIMAP_PADDING = 20


def _dark_bg(size: int) -> Image.Image:
    """Simple dark background when no cell image exists."""
    img = Image.new("RGB", (size, size), (18, 22, 28))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        c = int(18 + (y / size) * 8)
        draw.line([(0, y), (size, y)], fill=(c, c + 2, c + 5))
    return img


def _load_bg(image_url: str | None) -> Image.Image:
    """Load cell background image or return dark gradient."""
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
    size = 10
    cs = MINIMAP_CELL
    bw = size * cs + 4
    bh = size * cs + 4

    # Border
    draw.rectangle([ox - 2, oy - 2, ox + bw + 2, oy + bh + 2], fill=(40, 35, 30), outline=(180, 160, 100), width=2)

    for cy in range(size):
        for cx in range(size):
            cell = next((c for c in cells if c.x == cx and c.y == cy), None)
            px = ox + cx * cs
            py = oy + cy * cs

            if cx == player_x and cy == player_y:
                color = (0, 255, 100)      # Player
            elif cell is None or not cell.is_passable:
                color = (20, 20, 25)       # Wall
            elif cell.mob_id:
                color = (220, 50, 50)      # Enemy
            elif cell.has_npc:
                color = (255, 200, 50)     # NPC
            elif cell.has_chest:
                color = (150, 50, 220)     # Chest
            else:
                t = cell.tile_type or "grass"
                color = {
                    "grass": (45, 100, 45),
                    "forest": (25, 70, 25),
                    "water": (35, 60, 110),
                    "road": (80, 70, 45),
                    "village": (90, 80, 45),
                    "cave": (45, 40, 55),
                    "wall": (20, 20, 25),
                }.get(t, (45, 100, 45))

            draw.rectangle([px, py, px + cs - 2, py + cs - 2], fill=color)


def render_cell_image(cell, cells, player_x: int, player_y: int, output_path: str) -> str:
    img = _load_bg(cell.image_url)
    draw = ImageDraw.Draw(img)

    # Center minimap
    mm_size = 10 * MINIMAP_CELL
    mm_x = (TILE_SIZE - mm_size) // 2
    mm_y = (TILE_SIZE - mm_size) // 2 - 30
    _draw_minimap(draw, cells, player_x, player_y, mm_x, mm_y)

    # Fonts
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
    except:
        font = small = ImageFont.load_default()

    # Cell name top
    draw.text((MINIMAP_PADDING, 12), cell.name, fill=(255, 255, 255),
              font=font, stroke_width=2, stroke_fill=(0, 0, 0))

    # Coords bottom
    draw.text((MINIMAP_PADDING, TILE_SIZE - 28), f"[{cell.x},{cell.y}]", fill=(200, 200, 200),
              font=font, stroke_width=2, stroke_fill=(0, 0, 0))

    # Legend under minimap
    ly = mm_y + mm_size + 15
    legends = [
        ("Ty", (0, 255, 100)),
        ("Vrag", (220, 50, 50)),
        ("NPC", (255, 200, 50)),
        ("Sunduk", (150, 50, 220)),
    ]
    lx = mm_x
    for text, color in legends:
        draw.rectangle([lx, ly, lx + 10, ly + 10], fill=color)
        draw.text((lx + 14, ly - 1), text, fill=(255, 255, 255), font=small)
        lx += 70

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
