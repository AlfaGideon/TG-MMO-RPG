import os
import json
from PIL import Image, ImageDraw
from sqlalchemy import select
from core.database import async_session
from core.models import UILayout

# Путь к статике админки (от корня проекта)
STATIC_ROOT = "admin"

async def render_ui(layout_key: str, items_map: dict, output_path: str):
    """Отрисовывает интерфейс через Pillow.

    layout_key: ключ из таблицы ui_layouts.
    items_map: словарь {имя_слота: путь_к_картинке_предмета}.
    output_path: куда сохранить результат.
    """
    async with async_session() as session:
        result = await session.execute(
            select(UILayout).where(UILayout.key == layout_key)
        )
        layout = result.scalar_one_or_none()
        if not layout:
            return False

    bg_path = layout.image_url.lstrip("/")
    if not os.path.exists(os.path.join(STATIC_ROOT, bg_path)):
        # Попробуем без STATIC_ROOT если путь абсолютный
        if not os.path.exists(bg_path):
             return False
        full_bg_path = bg_path
    else:
        full_bg_path = os.path.join(STATIC_ROOT, bg_path)

    bg = Image.open(full_bg_path).convert("RGBA")
    slots = json.loads(layout.slots_json)

    for slot in slots:
        slot_name = slot["name"]
        item_img_path = items_map.get(slot_name)
        
        if item_img_path:
            # Превращаем /static/... в admin/static/...
            if item_img_path.startswith("/static/"):
                item_full_path = os.path.join(STATIC_ROOT, item_img_path.lstrip("/"))
            else:
                item_full_path = item_img_path

            if os.path.exists(item_full_path):
                item_icon = Image.open(item_full_path).convert("RGBA")
                # Ресайзим иконку под размер слота
                item_icon = item_icon.resize((slot["w"], slot["h"]), Image.LANCZOS)
                # Накладываем на фон
                bg.paste(item_icon, (slot["x"], slot["y"]), item_icon)

    bg.save(output_path, "PNG")
    return True
