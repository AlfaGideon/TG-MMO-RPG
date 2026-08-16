"""Раздел будущих питомцев и сохранённые концепт-листы."""
import asyncio
import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Грейсфул-скип: без этих пакетов набор не падает ImportError, а
# честно печатает «⚠ Пропуск» и выходит с кодом 0 (см. tests/_deps.py).
from _deps import require  # noqa: E402

require("fastapi", "PIL", "sqlalchemy", "aiosqlite")
FAILED = []


def check(value, label):
    print(("  ✅ " if value else "  ❌ ") + label)
    if not value:
        FAILED.append(label)


def test_concept_sheets():
    from PIL import Image
    from core import pets
    from engine import data

    print("\n— Концепты перенесены к питомцам —")
    urls = pets.available_concept_sheets()
    check(len(urls) == 7, "сохранены семь исходных листов 3×3")
    paths = [ROOT / "admin/static" / url.removeprefix("/static/") for url in urls]
    check(all(path.is_file() for path in paths), "все листы доступны через /static/pets")
    check(all(Image.open(path).size == (1536, 1536) for path in paths),
          "листы пригодны для последующей ручной нарезки")
    check(not list((ROOT / "admin/static/mobs").glob("*_slime.jpg")),
          "старые круглые слаймы больше не назначены боевым мобам")
    check(not any(row[0].startswith("Слайм-") for row in data.MOBS),
          "оригинальные имена монстров восстановлены")


def test_admin_wiring():
    print("\n— Питомцы в админ-панели —")
    base = (ROOT / "admin/templates/base.html").read_text(encoding="utf-8")
    hub = (ROOT / "admin/templates/content.html").read_text(encoding="utf-8")
    page = (ROOT / "admin/templates/editor_pets.html").read_text(encoding="utf-8")
    check('href="/editor/pets"' in base and 'href="/editor/pets"' in hub,
          "ссылка есть в меню и обзоре Контента")
    check("concept_sheets" in page and "/editor/pets/new" in page,
          "страница показывает листы и форму нового питомца")
    check('name="image"' in page and 'name="bonuses_json"' in page,
          "можно загрузить картинку и сохранить будущие бонусы")

    try:
        import admin.main as main
        routes = {
            (getattr(route, "path", ""),
             ",".join(sorted(getattr(route, "methods", None) or [])))
            for route in main.app.routes
            if getattr(route, "path", "")
        }
        check(any(path == "/editor/pets" for path, _ in routes), "GET /editor/pets подключён")
        check(any(path == "/editor/pets/new" for path, _ in routes), "POST создания подключён")
        check(any(path == "/editor/pets/{pet_id}/edit" for path, _ in routes), "POST редактирования подключён")
    except Exception as exc:
        check(False, f"роуты панели импортируются: {exc}")


async def test_model():
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from core.database import Base
    from core.models import PetTemplate
    from core import pets

    print("\n— Модель будущего питомца —")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        pet = PetTemplate(
            key=pets.normalize_key("Призрачный слизеволк"),
            name="Призрачный слизеволк", family="slimewolf", rarity="rare",
            slime_trait="прозрачная слизь",
            bonuses_json=pets.normalize_bonuses('{"crit_bonus":5}'),
        )
        session.add(pet)
        await session.commit()
        saved = (await session.execute(select(PetTemplate))).scalar_one()
        check(saved.key and saved.rarity == "rare", "питомец сохраняется в БД")
        check('"crit_bonus":5' in saved.bonuses_json, "черновые бонусы валидируются")
    await engine.dispose()


def main():
    needed = ("PIL", "sqlalchemy", "aiosqlite", "fastapi")
    missing = [name for name in needed if importlib.util.find_spec(name) is None]
    if missing:
        print("⚠️ ПРОПУСК: " + ", ".join(missing))
        return 0
    test_concept_sheets()
    test_admin_wiring()
    asyncio.run(test_model())
    print()
    if FAILED:
        print("❌ Провалено: " + ", ".join(FAILED))
        return 1
    print("✅ Раздел питомцев готов")
    return 0


if __name__ == "__main__":
    sys.exit(main())
