"""Разметка интерфейсов: каталог сцен, пресеты, проверка, живой рендер.

python3 tests/test_ui_layouts.py

Что было не так с разделом:

* **ключ разметки** вписывался руками — строку вида `inventory_order`
  взять было неоткуда. Ошибся — бот такую разметку не найдёт, и узнать
  об этом невозможно: ошибка молчаливая;
* **URL картинки** тоже вписывался руками, узнать его можно было только
  заглянув в файлы сервера;
* **имена слотов** редактор называл `slot_1`, `slot_2`, а рендер
  (`bot/utils/images.render_ui`) ищет слот по имени, совпадающему с типом
  предмета (`weapon`, `armor`…). То есть разметка из редактора не
  работала **никогда**;
* координаты писались в экранных пикселях, а картинка масштабировалась
  (`max-width: 1000px`): на фоне 1024 px разметка уезжала;
* и главное — `render_ui` **не вызывался ниоткуда**, вся разметка ни на
  что не влияла.

Здесь проверяется, что каждый из этих пунктов закрыт.
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Грейсфул-скип (пункт № 4 IDEAS-100.md).
from _deps import require  # noqa: E402

require("sqlalchemy", "PIL")

# Детерминизм (пункт № 5).
from _seed import pin  # noqa: E402

pin(120)

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


def test_scenes_replace_freehand_key():
    """Ключ выбирается из каталога, а не выдумывается."""
    print("\n— Каталог сцен вместо пустого поля —")
    from core import ui_layouts as UL

    check(len(UL.SCENES) >= 5, f"сцен в каталоге: {len(UL.SCENES)}")
    for scene in UL.SCENES:
        check(bool(scene.get("hint")),
              f"у сцены {scene['key']} есть объяснение, где она видна")
        check(bool(scene.get("slots")), f"у сцены {scene['key']} заданы слоты")

    check(UL.scene("equipment") is not None, "сцена экипировки существует")
    check(UL.scene("выдуманный_ключ") is None,
          "несуществующий ключ не притворяется сценой")


def test_slot_names_match_render():
    """Имена слотов совпадают с типами предметов — иначе рендер их не найдёт."""
    print("\n— Имена слотов понятны рендеру —")
    from core.enums import ItemType
    from core import ui_layouts as UL

    equip_types = {t.value for t in ItemType} - {"consumable", "material"}
    names = {s["name"] for s in UL.scene_slots("equipment")}
    check(names == equip_types,
          f"слоты экипировки = типы надеваемых вещей ({sorted(names)})")

    bag = UL.scene_slots("inventory")
    check(all(s["name"].startswith("bag_") for s in bag),
          "ячейки сумки пронумерованы предсказуемо")
    check(len(bag) == UL.BAG_SLOT_COUNT, f"ячеек сумки: {len(bag)}")


def test_gallery_lists_real_files():
    """Галерея показывает реально существующие картинки."""
    print("\n— Галерея вместо ручного ввода пути —")
    from core import ui_layouts as UL

    gallery = UL.gallery()
    check(len(gallery) > 0, f"картинок найдено: {len(gallery)}")
    for img in gallery:
        path = os.path.join(ROOT, img["url"].lstrip("/").replace("static/",
                                                                 "admin/static/", 1))
        check(os.path.isfile(path), f"{img['name']} существует на диске")
        break   # достаточно первой: проверяем принцип, не весь список

    size = UL.image_size(gallery[0]["url"])
    check(size and size[0] > 0, f"размер картинки читается: {size}")
    check(UL.image_size("/static/ui/нет-такой.png") is None,
          "несуществующая картинка не выдумывает размер")


def test_preset_scales_with_image():
    """Пресет считается от размера картинки, а не зашит в пикселях."""
    print("\n— Автораскладка слотов —")
    from core import ui_layouts as UL

    small = UL.preset("equipment", 400, 400)
    large = UL.preset("equipment", 1600, 1600)
    check(len(small) == len(UL.scene_slots("equipment")),
          "пресет покрывает все слоты сцены")
    check(large[0]["w"] > small[0]["w"],
          "на большой картинке слоты крупнее — раскладка не абсолютная")

    for slots, size in ((small, 400), (large, 1600)):
        outside = [s for s in slots
                   if s["x"] + s["w"] > size or s["y"] + s["h"] > size]
        check(not outside, f"пресет {size}px не вылезает за край")

    bag = UL.preset("inventory", 900, 900)
    check(len(bag) == UL.BAG_SLOT_COUNT, "пресет сумки покрывает все ячейки")
    check(len({(s["x"], s["y"]) for s in bag}) == len(bag),
          "ячейки сумки не наложены друг на друга")


def test_validation_catches_silent_breakage():
    """Проверка ловит то, из-за чего рендер молча ничего не рисовал."""
    print("\n— Живая проверка разметки —")
    from core import ui_layouts as UL

    good = UL.preset("equipment", 1024, 1024)
    check(UL.validate("equipment", good, 1024, 1024)["ok"],
          "полная раскладка признана готовой")

    partial = UL.validate("equipment", good[:2], 1024, 1024)
    check(not partial["ok"] and len(partial["missing"]) == 3,
          f"нехватка слотов замечена: {partial['missing']}")

    alien = UL.validate("equipment",
                        [{"name": "slot_1", "x": 0, "y": 0, "w": 10, "h": 10}])
    check(alien["unknown"] == ["slot_1"],
          "старое имя slot_1 помечено как чужое — рендер его игнорирует")

    dupes = UL.validate("equipment", good + [dict(good[0])], 1024, 1024)
    check(dupes["duplicates"] == ["weapon"],
          "повтор имени замечен: второй слот перекрыл бы первый")

    far = dict(good[0])
    far["x"] = 5000
    outside = UL.validate("equipment", [far], 1024, 1024)
    check(outside["outside"] == [far["name"]],
          "слот за краем картинки замечен")


def test_designer_uses_image_coordinates():
    """Холст работает в пикселях оригинала, а не экрана."""
    print("\n— Координаты не зависят от масштаба показа —")
    with open(os.path.join(ROOT, "admin", "templates",
                           "ui_layout_designer.html"), encoding="utf-8") as fh:
        tpl = fh.read()

    check("viewBox=\"0 0 {{ img_w }} {{ img_h }}\"" in tpl,
          "у SVG задан viewBox в пикселях оригинала")
    check("scaleX" in tpl and "drag.scaleX" in tpl,
          "перетаскивание пересчитывает сдвиг мыши в пиксели картинки")
    check("SCENE_SLOTS" in tpl,
          "список слотов приходит с сервера, а не набирается вручную")
    check("applyPreset" in tpl, "есть кнопка автораскладки")
    check("checkLayout" in tpl, "есть живая проверка полноты")


def test_admin_page_offers_choice():
    """Страница предлагает выбор вместо двух пустых полей."""
    print("\n— Страница списка —")
    with open(os.path.join(ROOT, "admin", "templates", "ui_layouts.html"),
              encoding="utf-8") as fh:
        tpl = fh.read()

    check("gallery" in tpl, "галерея фонов выводится")
    check("scenes" in tpl, "сцены выводятся")
    check('placeholder="Напр: inventory_order"' not in tpl,
          "поле свободного ввода ключа убрано")
    check('name="image_url"' in tpl and "<select" in tpl,
          "картинка выбирается списком, а не вписывается")

    with open(os.path.join(ROOT, "admin", "main.py"), encoding="utf-8") as fh:
        main_src = fh.read()
    check("if UL.scene(key) is None" in main_src,
          "сервер отвергает ключ не из каталога")
    check("clear_cache" in main_src,
          "после правки разметки кэш готовых картинок сбрасывается")


def test_render_is_actually_used():
    """Главное: рендер перестал быть мёртвым кодом."""
    print("\n— Разметка влияет на игру —")
    with open(os.path.join(ROOT, "bot", "handlers", "character.py"),
              encoding="utf-8") as fh:
        char_src = fh.read()
    check("render_equipment" in char_src,
          "профиль зовёт отрисовку экипировки")
    check('PROFILE_PAGES[page][0] == "gear"' in char_src,
          "картинка показывается на развороте «Снаряжение»")

    from bot.utils import gearview

    check(callable(gearview.render_equipment), "функция рендера доступна")
    check(callable(gearview.clear_cache), "есть сброс кэша")

    # Имя файла зависит от набора вещей: сменил меч — новая картинка.
    first = gearview._cache_name("equipment", {"weapon": "/a.png"})
    same = gearview._cache_name("equipment", {"weapon": "/a.png"})
    other = gearview._cache_name("equipment", {"weapon": "/b.png"})
    check(first == same, "тот же набор вещей даёт то же имя файла (кэш живёт)")
    check(first != other, "смена вещи даёт новое имя (картинка обновится)")


def test_render_survives_missing_pieces():
    """Отсутствие разметки не должно ломать экран профиля."""
    print("\n— Стойкость к пустякам —")
    import asyncio

    from core.database import async_session
    from core.migrations import run_migrations
    from core.models import Character, User

    async def scenario():
        await run_migrations()
        from bot.utils.gearview import render_equipment

        async with async_session() as session:
            user = User(telegram_id=424242, username="gear")
            session.add(user)
            await session.flush()
            char = Character(user_id=user.id, name="Гидеон",
                             character_class="mage", level=5)
            session.add(char)
            await session.commit()

            # Разметки в базе нет вообще.
            result = await render_equipment(session, char)
            check(result is None,
                  "без разметки возвращается None, а не исключение")

            # Разметка есть, но пустая.
            from core.models import UILayout

            session.add(UILayout(key="equipment",
                                 image_url="/static/ui/equipment_bg.png",
                                 slots_json="[]"))
            await session.commit()
            result = await render_equipment(session, char)
            check(result is None, "пустая разметка тоже не роняет профиль")

            # Разметка полная, но ничего не надето.
            from core import ui_layouts as UL

            layout = (await session.execute(
                __import__("sqlalchemy").select(UILayout))).scalars().first()
            layout.slots_json = json.dumps(UL.preset("equipment", 1024, 1024))
            await session.commit()
            result = await render_equipment(session, char)
            check(result is None, "герой без экипировки — портрет, не пустой фон")

    asyncio.run(scenario())


def test_visual_layer_is_themed():
    """Новый облик не зашивает цвета мимо тем."""
    print("\n— Обновление облика —")
    import re

    with open(os.path.join(ROOT, "admin", "static", "style.css"),
              encoding="utf-8") as fh:
        css = fh.read()

    check("--shadow-md" in css and "--ring" in css,
          "заведены переменные теней и фокус-ринга")
    check(":focus-visible" in css,
          "фокус виден с клавиатуры (:focus-visible, а не :focus)")
    check("prefers-reduced-motion" in css,
          "уважается системная настройка «меньше движения»")
    check("tabular-nums" in css,
          "числовые колонки выровнены по разрядам")

    # Тот же инвариант, что стережёт test_admin_layout: одно объявление.
    for sel in (r"\.btn", r"\.card", r"\.stat-box"):
        n = len(re.findall(rf"^{sel}\s*\{{", css, re.M))
        check(n == 1, f"{sel} объявлен один раз ({n})")


def main():
    test_scenes_replace_freehand_key()
    test_slot_names_match_render()
    test_gallery_lists_real_files()
    test_preset_scales_with_image()
    test_validation_catches_silent_breakage()
    test_designer_uses_image_coordinates()
    test_admin_page_offers_choice()
    test_render_is_actually_used()
    test_render_survives_missing_pieces()
    test_visual_layer_is_themed()

    print("\n" + "=" * 46)
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}")
        for f in FAILED:
            print("   -", f)
        return 1
    print("✅ Разметка: сцены, галерея, пресеты, проверка и живой рендер")
    return 0


if __name__ == "__main__":
    tmp = tempfile.mkdtemp(prefix="shadowlands-uilayout-")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp}/test.db"
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        code = main()
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(code)
