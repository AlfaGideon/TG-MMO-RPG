"""Строгие top-down обзоры четырёх фракционных замков.

Каждый файл — карта 25×25 клеток: замковый квартал занимает ровно 10×10
клеток в соответствующем углу. Подходы к нему только ортогональные; никакой
диагональной дороги в этих обзорных картах нет.
"""
from sqlalchemy import select

from core.models import Location


CASTLE_IMAGES = {
    "Замок Рассвета": "/static/castles/order_castle_25.png",
    "Замок Теней": "/static/castles/cult_castle_25.png",
    "Замок Глубин": "/static/castles/scavengers_castle_25.png",
    "Замок Пепла": "/static/castles/guard_castle_25.png",
}

# Пустой URL и стандартная безопасная заглушка можно безопасно заменить.
# Внешний/ручной URL админа не трогаем.
_DEFAULT_SAFE_MARKER = "loc1_safe.jpg"


def castle_image(name: str | None) -> str:
    """Top-down картинка замка по названию локации."""
    return CASTLE_IMAGES.get((name or "").strip(), "")


async def ensure_castle_images(session) -> int:
    """Поставить обзоры замков на старый сид, не затирая ручные фоны."""
    result = await session.execute(
        select(Location).where(Location.name.in_(tuple(CASTLE_IMAGES)))
    )
    changed = 0
    for location in result.scalars():
        current = (location.image_url or "").strip()
        if current and _DEFAULT_SAFE_MARKER not in current:
            continue
        image = castle_image(location.name)
        if image and current != image:
            location.image_url = image
            changed += 1
    return changed
