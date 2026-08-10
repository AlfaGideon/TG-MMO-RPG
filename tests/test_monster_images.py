"""Одиночные полноразмерные портреты боевых монстров."""
import asyncio
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FAILED = []


def check(value, label):
    print(("  ✅ " if value else "  ❌ ") + label)
    if not value:
        FAILED.append(label)


def test_files():
    from PIL import Image
    from core.mob_images import MOB_IMAGES, mob_image_url
    from engine import data

    print("\n— Полноразмерные боевые монстры —")
    check(len(set(MOB_IMAGES.values())) == 46,
          "готовы пять серий — 46 полноразмерных портретов")
    paths = [ROOT / "admin/static/mobs" / filename for filename in set(MOB_IMAGES.values())]
    check(all(path.is_file() and path.stat().st_size > 150_000 for path in paths),
          "все изображения настоящие, не заглушки")
    sizes = [Image.open(path).size for path in paths]
    check(all(w == h and w >= 1024 for w, h in sizes),
          "каждый портрет одиночный, квадратный и высокого разрешения")
    check(mob_image_url("Лесной ворг").endswith("forest_worg.jpg"),
          "сервер сопоставляет ворга с правильным портретом")
    check(data.mob_battle_image(6, browser=True).endswith("skeleton_warrior.jpg"),
          "браузер сопоставляет скелета с правильным портретом")
    check(mob_image_url("Пожиратель миров").endswith("world_devourer.jpg"),
          "финальный босс получил отдельный полноразмерный портрет")
    check(data.mob_battle_image(38, browser=True).endswith("carrion_harpy.jpg"),
          "гарпия подключена к браузерному бою")
    check(not any(row[0].startswith("Слайм-") for row in data.MOBS),
          "монстры сохранили исходные имена и анатомические виды")


async def test_backfill():
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from core.database import Base
    from core.mob_images import ensure_mob_images
    from core.models import Mob

    print("\n— Автопривязка к старой БД —")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        zombie = Mob(name="Болотный зомби", description="", level=1)
        custom = Mob(name="Лесной ворг", description="", level=2,
                     image_url="https://artist.example/worg.jpg")
        session.add_all((zombie, custom))
        await session.flush()
        changed = await ensure_mob_images(session)
        check(changed == 1 and zombie.image_url.endswith("swamp_zombie.jpg"),
              "пустой портрет автоматически заполнен")
        check(custom.image_url == "https://artist.example/worg.jpg",
              "ручной арт администратора не затёрт")
    await engine.dispose()


def main():
    missing = [m for m in ("PIL", "sqlalchemy", "aiosqlite")
               if importlib.util.find_spec(m) is None]
    if missing:
        print("⚠️ ПРОПУСК: " + ", ".join(missing))
        return 0
    test_files()
    asyncio.run(test_backfill())
    print()
    if FAILED:
        print("❌ Провалено: " + ", ".join(FAILED))
        return 1
    print("✅ Первая серия боевых монстров готова")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
