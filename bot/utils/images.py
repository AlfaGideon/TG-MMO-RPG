"""Рендер интерфейсных фонов Pillow по разметке из админки."""
import json

from PIL import Image
from sqlalchemy import select

from core.assets import local_asset_path
from core.database import async_session
from core.models import UILayout


async def render_ui(layout_key: str, items_map: dict, output_path: str):
    """Отрисовать интерфейс с предметами по сохранённой разметке.

    ``items_map``: ``{имя_слота: путь_к_картинке_предмета}``. Пути `/static`
    вычисляются от корня проекта, поэтому функция одинаково работает локально
    и внутри контейнера.
    """
    async with async_session() as session:
        result = await session.execute(
            select(UILayout).where(UILayout.key == layout_key)
        )
        layout = result.scalar_one_or_none()
        if not layout:
            return False

    bg_path = local_asset_path(layout.image_url)
    if not bg_path or not bg_path.is_file():
        return False

    bg = Image.open(bg_path).convert("RGBA")
    try:
        slots = json.loads(layout.slots_json or "[]")
    except (TypeError, ValueError):
        return False

    for slot in slots:
        slot_name = slot.get("name", "")
        item_path = local_asset_path(items_map.get(slot_name))
        if not item_path or not item_path.is_file():
            continue

        # Старые разметки могли иметь только `size`; новые — w/h.
        width = int(slot.get("w", slot.get("size", 80)))
        height = int(slot.get("h", slot.get("size", 80)))
        if width <= 0 or height <= 0:
            continue
        item_icon = Image.open(item_path).convert("RGBA")
        item_icon = item_icon.resize((width, height), Image.LANCZOS)
        bg.paste(item_icon, (int(slot.get("x", 0)), int(slot.get("y", 0))),
                 item_icon)

    bg.save(output_path, "PNG")
    return True
