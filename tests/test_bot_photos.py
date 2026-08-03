"""Регрессии локальных картинок Telegram-бота.

Проверяет именно проблему «файлы лежат в репозитории, но бот шлёт текст»:
пути `/static/...` не должны зависеть от текущей рабочей папки процесса,
а стандартные портреты NPC должны попадать и в старые базы.

python3 tests/test_bot_photos.py
"""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAILED = []


def check(condition, label):
    print(("  ✅ " if condition else "  ❌ ") + label)
    if not condition:
        FAILED.append(label)


def _have(*modules):
    import importlib.util
    return all(importlib.util.find_spec(module) for module in modules)


def test_static_resolver():
    from core.assets import REPO_ROOT, local_asset_path
    from core import ui_images

    print("\n— Пути статики —")
    check(REPO_ROOT == ROOT, "корень ассетов вычисляется от модуля, не от cwd")
    npc = local_asset_path("/static/npcs/eduard.jpg")
    check(npc == ROOT / "admin/static/npcs/eduard.jpg" and npc.is_file(),
          "/static/npcs/eduard.jpg указывает на реальный файл")
    # Cache-buster в URL панели не должен ломать локальную картинку.
    cached = local_asset_path("/static/branding/help.png?v=123")
    check(cached == ROOT / "admin/static/branding/help.png" and cached.is_file(),
          "cache-buster не ломает путь к картинке")
    check(local_asset_path("../../etc/passwd") is None,
          "относительный путь не может выйти из проекта")
    check(all(ui_images._usable(ui_images.DEFAULTS[key])
              for key in ("offline", "help", "ideas", "updates", "inventory")),
          "все новые экраны имеют доступный запасной файл")


def test_photo_input_independent_of_cwd():
    from bot.utils.photos import get_photo_input, has_usable_photo

    print("\n— Фото aiogram —")
    before = Path.cwd()
    try:
        os.chdir("/")
        photo = get_photo_input("/static/npcs/eduard.jpg")
        check(photo is not None, "бот находит NPC-портрет вне корня проекта")
        path = Path(str(getattr(photo, "path", "")))
        check(path == ROOT / "admin/static/npcs/eduard.jpg",
              "в FSInputFile передан абсолютный путь")
        check(has_usable_photo("/static/ui/inventory_bg.png"),
              "фоновая картинка инвентаря доступна")
        check(not has_usable_photo("/static/npcs/does-not-exist.jpg"),
              "отсутствующий файл не маскируется под фото")
    finally:
        os.chdir(before)


def test_npc_defaults():
    from core.npc_images import NPC_FILES, npc_image_url

    print("\n— Стандартные портреты NPC —")
    urls = [npc_image_url(name) for name in NPC_FILES]
    check(all(url.startswith("/static/npcs/") for url in urls),
          f"у всех {len(urls)} именных NPC есть путь")
    check(all((ROOT / "admin/static" / url.removeprefix("/static/")).is_file()
              for url in urls),
          "каждый путь именного NPC указывает на существующий файл")
    check(npc_image_url("Кастелян Одо", "Замок Рассвета").endswith("order_npc.jpg"),
          "авторский NPC получает фракционный запасной портрет")


async def test_npc_backfill():
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from core.database import Base
    from core.models import Cell, Location
    from core.npc_images import ensure_npc_images

    print("\n— Накат портретов на старую БД —")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        loc = Location(name="Замок Рассвета", description="")
        session.add(loc)
        await session.flush()
        blank = Cell(location_id=loc.id, x=0, y=0, has_npc=True,
                     npc_name="Инквизитор Эдуард")
        manual = Cell(location_id=loc.id, x=1, y=0, has_npc=True,
                      npc_name="Кастелян Одо", image_url="https://example.test/own.jpg")
        session.add_all((blank, manual))
        await session.flush()
        changed = await ensure_npc_images(session)
        check(changed == 1, "заполнена ровно одна пустая картинка")
        check(blank.image_url == "/static/npcs/eduard.jpg",
              "старый NPC получил свой портрет")
        check(manual.image_url == "https://example.test/own.jpg",
              "ручной URL администратора не затёрт")
    await engine.dispose()


def main():
    if not _have("aiogram", "sqlalchemy", "aiosqlite"):
        print("⚠️  ПРОПУСК: нужны aiogram, sqlalchemy и aiosqlite")
        return 0

    test_static_resolver()
    test_photo_input_independent_of_cwd()
    test_npc_defaults()
    asyncio.run(test_npc_backfill())

    print()
    if FAILED:
        print("❌ Провалено: " + ", ".join(FAILED))
        return 1
    print("✅ Картинки бота доступны")
    return 0


if __name__ == "__main__":
    sys.exit(main())
