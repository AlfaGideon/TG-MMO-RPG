"""Стандартные полноразмерные портреты боевых монстров.

Монстр сохраняет собственную анатомию, а слизь является материалом тела.
Ручная картинка из админки всегда имеет приоритет над этими дефолтами.
"""
from sqlalchemy import select

from core.assets import local_asset_exists
from core.models import Mob


MOB_IMAGES = {
    "Помойная крыса": "garbage_rat.jpg",
    "Болотный зомби": "swamp_zombie.jpg",
    "Лесной ворг": "forest_worg.jpg",
    "Паук-ткач": "weaver_spider.jpg",
    "Леший-обманщик": "trickster_leshy.jpg",
    "Гнилой вепрь": "rotten_boar.jpg",
    "Скелет-воин": "skeleton_warrior.jpg",
    "Гнолл-грабитель": "gnoll_raider.jpg",
    "Ржавый латник": "rusty_knight.jpg",
    "Стрелок-мародёр": "marauder_marksman.jpg",
    "Пёс войны": "war_hound.jpg",
    "Пещерный тролль": "cave_troll.jpg",
    "Теневой призрак": "shadow_ghost.jpg",
    "Костяной жрец": "bone_priest.jpg",
    "Могильный червь": "grave_worm.jpg",
    "Плакальщица": "banshee_mourner.jpg",
    "Голем из костей": "bone_golem.jpg",
    "Культист Бездны": "abyss_cultist.jpg",
    "Порождение бездны": "abyss_spawn.jpg",
    "Страж расщелины": "rift_guardian.jpg",
    "Разбойник с большой дороги": "marauder_marksman.jpg",
    "Скальный хищник": "rock_predator.jpg",
    "Пепельный волк": "ash_wolf.jpg",
    "Мёрзлый зомби": "frozen_zombie.jpg",
    "Ледяной падальщик": "ice_scavenger.jpg",
    "Северный канюк": "northern_buzzard.jpg",
    "Снежный волк": "snow_wolf.jpg",
    "Тёмный следопыт": "dark_tracker.jpg",
    "Костяной странник": "bone_wanderer.jpg",
    "Чернокнижник пепла": "ash_warlock.jpg",
    "Гниющий великан": "rotting_giant.jpg",
    "Трясинный голем": "mire_golem.jpg",
    "Камнекожий страж": "stone_skin_guardian.jpg",
    "Горный тролль-одиночка": "mountain_troll.jpg",
    "Могильный страж": "grave_guardian.jpg",
    "Гарпия-падальщица": "carrion_harpy.jpg",
    "Топяной змей": "bog_serpent.jpg",
    "Пожиратель миров": "world_devourer.jpg",
}


def mob_image_url(name: str | None) -> str:
    filename = MOB_IMAGES.get((name or "").strip(), "")
    if not filename:
        return ""
    url = f"/static/mobs/{filename}"
    return url if local_asset_exists(url) else ""


async def ensure_mob_images(session) -> int:
    """Заполнить только пустые картинки, не затирая выбор администратора."""
    mobs = (await session.execute(select(Mob))).scalars().all()
    changed = 0
    for mob in mobs:
        if (mob.image_url or "").strip():
            continue
        url = mob_image_url(mob.name)
        if url:
            mob.image_url = url
            changed += 1
    if changed:
        await session.flush()
    return changed
