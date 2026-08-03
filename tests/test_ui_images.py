"""Единый раздел картинок: настройки экранов бота (ui_image:*),
портреты классов по фракциям и регистрация админ-маршрутов.

python3 tests/test_ui_images.py
"""
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# default_faction_image смотрит файлы относительно корня репозитория.
os.chdir(ROOT)

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


# ── настройки экранов бота ──────────────────────────────────


def test_ui_defaults():
    from core import ui_images

    print("\n— Дефолты экранов бота —")
    check({"welcome_ru", "welcome_en", "auction", "leaderboard",
           "splash_winter", "splash_spring", "splash_summer",
           "splash_autumn"} <= set(ui_images.DEFAULTS),
          f"есть все экраны, включая сезонные {sorted(ui_images.DEFAULTS)}")
    check(all(v.startswith("/static/branding/")
              for v in ui_images.DEFAULTS.values()),
          "дефолты ведут в статику админки")
    check(set(ui_images.TITLES) == set(ui_images.DEFAULTS),
          "у каждого экрана есть русское название")
    check(ui_images.setting_key("auction") == "ui_image:auction",
          "ключ настройки с префиксом")


def test_seasonal_splash():
    from core import ui_images

    print("\n— Сезонные заставки —")
    seasons = [ui_images.season_key(m) for m in
               (12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)]
    check(seasons == ["splash_winter"] * 3 + ["splash_spring"] * 3
          + ["splash_summer"] * 3 + ["splash_autumn"] * 3,
          "месяцы верно раскладываются по сезонам")
    check(set(ui_images.SEASON_FLAVOR) ==
          set(ui_images.SEASON_BY_MONTH.values()),
          "у каждого сезона есть приправа-подпись")
    # Сезонные файлы на диске и квадратные (заставка 1:1).
    import struct
    for key in ("splash_winter", "splash_spring", "splash_summer",
                "splash_autumn"):
        path = "admin" + ui_images.DEFAULTS[key]
        check(ui_images._usable(ui_images.DEFAULTS[key]),
              f"{key}: файл на месте")
        with open(path, "rb") as fh:
            head = fh.read(24)
        w, h = struct.unpack(">II", head[16:24])
        check(w == h == 1024, f"{key} квадратный ({w}×{h})")


async def _ui_roundtrip_async():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from core.database import Base
    import importlib
    importlib.import_module("core.models")
    from core import ui_images

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)

    async with sm() as s:
        check(await ui_images.get(s, "auction") ==
              ui_images.DEFAULTS["auction"],
              "без настройки отдаётся дефолт")
        check(await ui_images.get(s, "unknown") == "",
              "неизвестный ключ пуст")
        await ui_images.set_value(s, "auction", "/static/uploads/ny.png")
        check(await ui_images.get(s, "auction") == "/static/uploads/ny.png",
              "праздничная замена сохранена и читается")
        await ui_images.set_value(s, "auction", "")
        check((await ui_images.get(s, "auction")).endswith("auction.png"),
              "сброс возвращает дефолт")
        # Сезонная заставка: декабрь → зима, июль → лето; праздничная
        # замена из админки побеждает сезонный файл.
        check((await ui_images.seasonal_splash(s, 12)).endswith(
              "start_winter.png"), "декабрь → зимняя заставка")
        check((await ui_images.seasonal_splash(s, 7)).endswith(
              "start_summer.png"), "июль → летняя заставка")
        await ui_images.set_value(s, "splash_winter",
                                  "https://cdn.example/ny24.png")
        got = await ui_images.seasonal_splash(s, 12)
        check(got == "https://cdn.example/ny24.png",
              "праздничная тема поверх зимней заставки")
        # Битая локальная ссылка не долетит до Telegram — откат на классику.
        await ui_images.set_value(s, "splash_winter", "/static/uploads/ghost.png")
        check((await ui_images.seasonal_splash(s, 12)).endswith("start_ru.png"),
              "несуществующий файл → классическая заставка")
    await engine.dispose()


# ── портреты классов по фракциям ────────────────────────────


def _cls(**kw):
    from types import SimpleNamespace
    base = dict(key="warrior", image_url="/uploads/base.png",
                faction_images="")
    base.update(kw)
    return SimpleNamespace(**base)


def test_faction_images_json():
    from core import classes as cc

    print("\n— JSON портретов фракций —")
    check(cc.faction_images(_cls(faction_images="не json")) == {},
          "битый JSON безопасно пуст")
    check(cc.faction_images(_cls(faction_images='[1,2]')) == {},
          "не-словарь отброшен")
    c = _cls()
    cc.save_faction_image(c, "guard", "/static/classes/warrior_guard.png")
    cc.save_faction_image(c, "cult", "/x.png")
    imgs = cc.faction_images(c)
    check(imgs == {"guard": "/static/classes/warrior_guard.png",
                   "cult": "/x.png"},
          f"две картинки сохранены {imgs}")
    cc.save_faction_image(c, "cult", "")
    check(cc.faction_images(c) ==
          {"guard": "/static/classes/warrior_guard.png"},
          "пустой url снимает портрет фракции")


def test_class_image_priority():
    from core import classes as cc

    print("\n— Приоритет портрета: сторона → дефолт-файл → база —")
    c = _cls()
    check(cc.class_image(None, "guard") == "", "без класса пусто")
    check(cc.class_image(c, None) == "/uploads/base.png",
          "без стороны — базовая картинка класса")
    # warrior_guard.png лежит в статике → файловый дефолт.
    got = cc.class_image(c, "guard")
    check(got == "/static/classes/warrior_guard.png",
          f"портрет текущей стороны из файла ({got})")
    check(cc.class_image(c, "guard") ==
          cc.default_faction_image("warrior", "guard"),
          "class_image и default_faction_image согласованы")
    # Своя загрузка из админки побеждает файловый дефолт.
    cc.save_faction_image(c, "guard", "/static/uploads/halloween.png")
    check(cc.class_image(c, "guard") == "/static/uploads/halloween.png",
          "праздничная замена из админки важнее файла")
    cc.save_faction_image(c, "guard", "")
    check(cc.class_image(c, "unknown_side") == "/uploads/base.png",
          "неизвестная сторона → откат на базу")


def test_default_files():
    from core import classes as cc

    print("\n— Сгенерированные портреты в статике —")
    classes = tuple(d["key"] for d in cc.DEFAULT_CLASSES)
    factions = ("guard", "scavengers", "cult", "order")
    found, missing = [], []
    for cls in classes:
        for fac in factions:
            url = cc.CLASS_FACTION_IMAGE_TEMPLATE.format(
                class_key=cls, faction=fac)
            on_disk = os.path.isfile("admin" + url)
            check(cc.default_faction_image(cls, fac) ==
                  (url if on_disk else ""),
                  f"{cls}/{fac}: файл и словарь согласованы")
            (found if on_disk else missing).append(f"{cls}_{fac}")
    print(f"     файлов: {len(found)}, нет ещё: {', '.join(missing) or '—'}")
    done = {n.split("_")[0] for n in found}
    check(len(done) == len(classes),
          f"все {len(classes)} классов покрыты портретами")
    check(not missing,
          f"полный комплект {len(classes)}×4 портретов ({len(found)})")
    check(len(found) == len(classes) * len(factions),
          f"ровно {len(classes) * len(factions)} файлов ({len(found)})")
    # Размеры: всё строго 1×1 (картинка-квадрат под профиль).
    import struct
    for cls in classes:
        for fac in factions:
            url = cc.CLASS_FACTION_IMAGE_TEMPLATE.format(
                class_key=cls, faction=fac)
            path = "admin" + url
            if not os.path.isfile(path):
                continue
            with open(path, "rb") as fh:
                head = fh.read(24)
            w, h = struct.unpack(">II", head[16:24])
            check(w == h, f"{cls}_{fac} квадратный ({w}×{h})")


# ── админ-маршруты раздела ──────────────────────────────────


def test_admin_routes():
    print("\n— Маршруты админки —")
    from admin.main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    check("/editor/images" in paths, "GET /editor/images")
    check("/editor/images/set" in paths, "POST /editor/images/set")
    from bot.handlers import start, auction, character  # noqa: F401
    check(True, "обработчики бота импортируются")


def main():
    test_ui_defaults()
    test_seasonal_splash()
    print("\n— Настройки в БД —")
    asyncio.run(_ui_roundtrip_async())
    test_faction_images_json()
    test_class_image_priority()
    test_default_files()
    test_admin_routes()
    print("\n" + "=" * 46)
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}:")
        for f in FAILED:
            print("   -", f)
        return 1
    print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
