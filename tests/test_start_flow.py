"""Порядок создания героя: СНАЧАЛА фракция, ПОТОМ класс — чтобы
картинки выбора класса подходили и под класс, и под знамя игрока.

python3 tests/test_start_flow.py
"""
import asyncio
import os
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


def _kb_data(markup):
    return [b.callback_data for row in markup.inline_keyboard
            for b in row if b.callback_data]


# ── клавиатуры несут фракцию суффиксом ──────────────────────


def test_keyboard_faction_suffix():
    from bot.keyboards.inline import (class_select_keyboard,
                                      confirm_class_keyboard)
    from types import SimpleNamespace as NS

    print("\n— Клавиатуры книги классов с фракцией —")
    classes = [NS(key="warrior", icon="🛡", name="Воин"),
               NS(key="mage", icon="🔮", name="Маг")]
    kb = class_select_keyboard(classes, page=0, faction="guard")
    data = _kb_data(kb)
    check("select_class:warrior:guard" in data,
          f"выбор класса несёт знамя ({data})")
    check("class_page:1:guard" in data, "листание несёт знамя")
    check("create_character" in data,
          "«назад» в новом порядке — к выбору фракции")
    check("main_menu" not in data, "прямого выхода в меню больше нет")

    kb_old = class_select_keyboard(classes, page=0)
    data_old = _kb_data(kb_old)
    check("select_class:warrior" in data_old
          and "class_page:1" in data_old,
          "старый формат (без фракции) не сломан")
    check("main_menu" in data_old, "старый «назад» — в меню")

    ck = confirm_class_keyboard("mage", back_page=1, faction="cult")
    cdata = _kb_data(ck)
    check("confirm_class:mage:cult" in cdata,
          f"подтверждение несёт знамя ({cdata})")
    check("class_page:1:cult" in cdata, "«другой класс» вернётся на страницу")


def test_class_book_text():
    from bot.handlers.start import _class_book_text
    from core.models import CharacterClassDef

    print("\n— Текст книги классов —")
    cls = CharacterClassDef(
        icon="🛡", name="Воин", key="warrior",
        affinity_chance=0.18, dual_affinity_chance=0.03,
        preferred_schools="", is_enabled=True,
        description="Тяжёлые доспехи.", base_strength=15,
        base_agility=8, base_intelligence=5, base_endurance=14,
        base_luck=8, base_hp=140, base_mp=30,
        growth_strength=2, growth_agility=1, growth_intelligence=0,
        growth_endurance=2, growth_luck=0, growth_hp=14, growth_mp=3)
    txt = _class_book_text(cls, 0, 10, faction="guard")
    check("Книга классов" in txt, "заголовок книги на месте")
    check("Твоя сторона" in txt and "Стража" in txt,
          "шапка показывает выбранное знамя")
    txt_none = _class_book_text(cls, 0, 10)
    check("Твоя сторона" not in txt_none, "без фракции шапки знамени нет")
    check(len(txt) < 1024, f"влезает в подпись к фото ({len(txt)})")


# ── интеграция: фракция выбрана первой, финал после статов ──


class StubEvent:
    """Заглушка сообщения Telegram: ловит отправленные фото/тексты."""

    def __init__(self, user_id=777):
        self.from_user = SimpleNamespace(id=user_id)
        self.photo = None
        self.sent = []

    async def delete(self):
        return None

    async def answer_photo(self, photo=None, caption=None,
                           reply_markup=None, parse_mode=None):
        self.sent.append({"kind": "photo", "photo": photo,
                          "caption": caption, "kb": reply_markup})

    async def answer(self, text=None, reply_markup=None, parse_mode=None):
        self.sent.append({"kind": "text", "caption": text,
                          "kb": reply_markup})


async def _flow_async():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from core.database import Base
    import importlib
    importlib.import_module("core.models")
    from core.models import (User, Character, Location, Cell,
                             CharacterClassDef, VisitedCell)
    from bot.handlers.start import _finalize_creation, _show_class_book

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)

    async with sm() as s:
        user = User(telegram_id=777)
        s.add(user)
        await s.flush()
        s.add(CharacterClassDef(
            key="warrior", name="Воин", icon="🛡", sort_order=10,
            description="Тяжёлые доспехи, мечи и щиты.",
            base_strength=15, base_agility=8, base_intelligence=5,
            base_endurance=14, base_luck=8, base_hp=140, base_mp=30,
            growth_strength=2, growth_agility=1, growth_intelligence=0,
            growth_endurance=2, growth_luck=0, growth_hp=14, growth_mp=3))
        loc = Location(name="Замок Пепла", description="Крепость стражи.",
                       grid_size=25, world_x=9, world_y=9)
        s.add(loc)
        await s.flush()
        s.add(Cell(location_id=loc.id, x=19, y=19, floor=0,
                   is_passable=True))
        hero = Character(user_id=user.id, name="Тестер",
                         character_class="warrior",
                         faction="guard",  # знамя выбрано ПЕРВЫМ шагом
                         stats_locked=True, rerolls_left=0,
                         reputation="", bronze=0, silver=0, gold=0,
                         strength=15, agility=8, intelligence=5,
                         endurance=14, luck=8,
                         max_hp=140, current_hp=140, max_mp=30,
                         current_mp=30, level=1, experience=0)
        s.add(hero)
        await s.commit()
        hero_id = hero.id

    # Финал после принятия статов: бонусы знамени + спавн в его замке.
    ev = StubEvent(user_id=777)
    async with sm() as s:
        hero = await s.get(Character, hero_id)
        await _finalize_creation(ev, s, hero, "guard")
        assert ev.sent, "финал должен отправить сообщение"
        shot = ev.sent[-1]
        check(shot["kind"] == "photo",
              "финал идёт с картинкой знамени")
        check("Замок Пепла" in (shot["caption"] or ""),
              "финал объявляет стартовую локацию")
        check("Стража" in (shot["caption"] or ""),
              "финал объявляет фракцию")
        assert hero.location_id is not None and hero.cell_id is not None
        check(hero.faction == "guard", "фракция закреплена")
        check(hero.endurance == 17,
              f"бонус знамени +3 ВЫН ({hero.endurance})")
        check(hero.bronze > 0, f"стартовая выдача {hero.bronze}🟤")
        from core import factions as core_factions
        check(core_factions.load(hero).get("guard") == 50,
              "репутация +50 записана")
        bronze1, visited1 = hero.bronze, None
        from sqlalchemy import select as _sel
        visited1 = len((await s.execute(
            _sel(VisitedCell).where(VisitedCell.character_id == hero_id)
        )).scalars().all())
        check(visited1 == 1, "стартовая клетка отмечена на карте")

        # Идемпотентность: повторный финал не выдаёт бонусы дважды.
        await _finalize_creation(ev, s, hero, "guard")
        check(hero.bronze == bronze1 and hero.endurance == 17,
              "повторный финал без дубликатов бонусов")
        visited2 = len((await s.execute(
            _sel(VisitedCell).where(VisitedCell.character_id == hero_id)
        )).scalars().all())
        check(visited2 == visited1, "клетка не дублируется")

    # Книга классов после выбора знамени: портрет стороны + суффиксы.
    # _show_class_book ходит в БД через глобальную sessionmaker бота —
    # подменяем её тестовой in-memory БД.
    import bot.handlers.start as start_mod
    start_mod.async_session = sm
    ev2 = StubEvent(user_id=777)
    await _show_class_book(ev2, 0, "guard")
    assert ev2.sent, "книга классов должна открыться"
    book = ev2.sent[-1]
    check(book["kind"] == "photo", "страница класса идёт с портретом")
    check("Твоя сторона" in (book["caption"] or ""),
          "страница класса знает знамя")
    data = _kb_data(book["kb"])
    check("select_class:warrior:guard" in data,
          f"кнопки книги несут знамя ({data})")
    from aiogram.types import FSInputFile
    photo = book["photo"]
    check(isinstance(photo, FSInputFile)
          and "warrior_guard.png" in str(photo.path),
          f"портрет класса под знамя ({photo})")

    # Без знамени (старые сообщения) — базовый портрет и формат данных.
    ev3 = StubEvent(user_id=777)
    await _show_class_book(ev3, 0, None)
    data3 = _kb_data(ev3.sent[-1]["kb"])
    check("select_class:warrior" in data3,
          "страница без знамя остаётся в старом формате")

    await engine.dispose()


def main():
    test_keyboard_faction_suffix()
    test_class_book_text()
    print("\n— Финал создания: спавн и бонусы знамени —")
    asyncio.run(_flow_async())
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
