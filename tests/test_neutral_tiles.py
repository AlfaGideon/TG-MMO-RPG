"""Нейтральные сцены движения: формы дорог и прозрачный Pillow-слой.

python3 tests/test_neutral_tiles.py
"""
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from PIL import Image
except ImportError:
    print("⚠️  ПРОПУСК: нет Pillow")
    sys.exit(0)

FAILED = []


def check(condition, label):
    print(("  ✅ " if condition else "  ❌ ") + label)
    if not condition:
        FAILED.append(label)


def cell(x, y, tile="road", passable=True, name="Тракт"):
    return SimpleNamespace(id=x * 10 + y + 1, x=x, y=y, tile_type=tile,
                           is_passable=passable, name=name, image_url="")


def test_road_shapes():
    from core.neutral_tiles import (ROAD_CROSS, ROAD_STRAIGHT, ROAD_T, ROAD_TURN,
                                    background_for)

    print("\n— Форма дорожного фона —")
    center = cell(1, 1)
    cross = [center, cell(0, 1), cell(2, 1), cell(1, 0), cell(1, 2)]
    check(background_for(center, cross) == (ROAD_CROSS, 0),
          "четыре соседа → перекрёсток")

    straight = [center, cell(0, 1), cell(2, 1)]
    check(background_for(center, straight) == (ROAD_STRAIGHT, 0),
          "север–юг → прямой вертикальный участок")

    horizontal = [center, cell(1, 0), cell(1, 2)]
    check(background_for(center, horizontal) == (ROAD_STRAIGHT, 90),
          "запад–восток → повёрнутый прямой участок")

    turn = [center, cell(2, 1), cell(1, 2)]
    check(background_for(center, turn) == (ROAD_TURN, 0),
          "юг–восток → базовый поворот")

    tee = [center, cell(2, 1), cell(1, 0), cell(1, 2)]
    check(background_for(center, tee) == (ROAD_T, 0),
          "три соседа → T-перекрёсток")


def test_castle_overviews():
    from core.castle_images import CASTLE_IMAGES

    print("\n— Фракционные замки 25×25 —")
    expected = {"Замок Рассвета", "Замок Теней", "Замок Глубин", "Замок Пепла"}
    check(set(CASTLE_IMAGES) == expected, "есть обзор для каждого замка фракции")
    for name, url in CASTLE_IMAGES.items():
        path = ROOT / "admin/static" / url.removeprefix("/static/")
        image = Image.open(path)
        check(image.size == (1000, 1000), f"{name}: поле 25×25 по 40px")


async def test_castle_backfill():
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from core.database import Base
    from core.castle_images import ensure_castle_images
    from core.models import Location

    print("\n— Накат фонов замков на старую БД —")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        generic = Location(name="Замок Рассвета", description="", image_url="https://x/loc1_safe.jpg")
        manual = Location(name="Замок Теней", description="", image_url="https://artist.example/cult.png")
        session.add_all((generic, manual))
        await session.flush()
        changed = await ensure_castle_images(session)
        check(changed == 1 and generic.image_url.endswith("order_castle_25.png"),
              "дефолтный безопасный фон заменяется обзором замка")
        check(manual.image_url == "https://artist.example/cult.png",
              "ручной фон замка не перезаписывается")
    await engine.dispose()


def test_terrain_assets_and_scene():
    from core.neutral_tiles import TILE_BACKGROUNDS, background_for
    from core.map_renderer import TILE_SIZE, render_cell_image

    print("\n— Нейтральные ландшафты и слой Pillow —")
    expected = {"grass", "forest", "desert", "swamp", "water", "cave"}
    check(expected <= set(TILE_BACKGROUNDS), "есть все заявленные типы ландшафта")
    for tile, url in TILE_BACKGROUNDS.items():
        path = ROOT / "admin/static" / url.removeprefix("/static/")
        check(path.is_file(), f"{tile}: фон существует")

    meadow = cell(0, 0, "grass", name="Поляна")
    check(background_for(meadow, [meadow])[0].endswith("meadow.png"),
          "трава получает нейтральный луг")

    output = ROOT / "data" / "test_neutral_scene.jpg"
    render_cell_image(meadow, [meadow], 0, 0, str(output),
                      background_url=TILE_BACKGROUNDS["grass"])
    image = Image.open(output)
    check(image.size == (TILE_SIZE, TILE_SIZE), "сцена собрана в размер Telegram-фона")
    # Центр занят тактическим полупрозрачным слоем, но фон снаружи остаётся
    # живым и не сводится к одноцветной заглушке.
    center = image.getpixel((256, 256))
    top = image.getpixel((500, 20))
    check(center != top, "Pillow-слой наложен поверх фонового арта")
    try:
        output.unlink()
    except OSError:
        pass


def main():
    test_road_shapes()
    test_castle_overviews()
    asyncio.run(test_castle_backfill())
    test_terrain_assets_and_scene()
    print()
    if FAILED:
        print("❌ Провалено: " + ", ".join(FAILED))
        return 1
    print("✅ Нейтральные сцены движения готовы")
    return 0


if __name__ == "__main__":
    sys.exit(main())
