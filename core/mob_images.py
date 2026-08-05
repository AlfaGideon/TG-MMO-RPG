"""Стандартные портреты монстров мира.

Картинка, которую администратор задал у моба, всегда имеет приоритет.
Этот модуль позволяет боту подставлять дефолтные портреты по имени моба,
если поле image_url в базе пустое.
"""
from sqlalchemy import select
from core.assets import local_asset_exists
from core.models import Mob


MOB_FILES = {
    "Помойная крыса": "rat.png",
    "Болотный зомби": "zombie.png",
    "Лесной ворг": "warg.png",
    "Паук-ткач": "spider.png",
    "Скелет-воин": "skeleton.png",
    "Гнолл-грабитель": "gnoll.png",
    "Ржавый латник": "rusty_knight.png",
    "Пещерный тролль": "troll.png",
    "Теневой призрак": "wraith.png",
    "Пожиратель Глубин": "boss_devourer.png",
}


def mob_image_url(mob_name: str | None) -> str:
    """Путь /static/mobs/... к стандартному портрету или пустая строка."""
    filename = MOB_FILES.get((mob_name or "").strip())
    if filename:
        url = f"/static/mobs/{filename}"
        return url if local_asset_exists(url) else ""
    return ""


async def ensure_mob_images(session) -> int:
    """Заполнить пустые портреты монстров на уже существующих базах."""
    result = await session.execute(
        select(Mob).where(Mob.image_url.is_(None))
    )
    changed = 0
    for mob in result.scalars():
        url = mob_image_url(mob.name)
        if url:
            mob.image_url = url
            changed += 1
    return changed
