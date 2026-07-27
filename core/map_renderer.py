import os
from PIL import Image, ImageDraw, ImageFont

TILE_SIZE = 512
MINIMAP_CELL = 36


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

    # Outer border
    draw.rectangle([ox - 2, oy - 2, ox + bw + 2, oy + bh + 2],
                   fill=(30, 30, 35), outline=(100, 100, 110), width=2)

    for cy in range(size):
        for cx in range(size):
            cell = next((c for c in cells if c.x == cx and c.y == cy), None)
            px = ox + cx * cs
            py = oy + cy * cs

            if cx == player_x and cy == player_y:
                # Player - bright white dot
                color = (220, 220, 220)
            elif cell is None or not cell.is_passable:
                # Wall - very dark
                color = (15, 15, 20)
            else:
                # All passable cells same color - no hints
                color = (60, 65, 70)

            draw.rectangle([px, py, px + cs - 2, py + cs - 2], fill=color)


def render_cell_image(cell, cells, player_x: int, player_y: int, output_path: str) -> str:
    img = _load_bg(cell.image_url)
    draw = ImageDraw.Draw(img)

    # Center minimap
    mm_size = 10 * MINIMAP_CELL
    mm_x = (TILE_SIZE - mm_size) // 2
    mm_y = (TILE_SIZE - mm_size) // 2 - 20
    _draw_minimap(draw, cells, player_x, player_y, mm_x, mm_y)

    # Fonts
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
    except:
        font = small = ImageFont.load_default()

    # Cell name top
    draw.text((20, 12), cell.name, fill=(255, 255, 255),
              font=font, stroke_width=2, stroke_fill=(0, 0, 0))

    # Coords bottom
    draw.text((20, TILE_SIZE - 28), f"[{cell.x},{cell.y}]", fill=(180, 180, 180),
              font=font, stroke_width=2, stroke_fill=(0, 0, 0))

    # No legend - player must explore

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
