"""Экраны бота: возврат к действию, книги, отделения сумки, VIP-меню.

Покрывает правки после жалоб игроков:
  1. после NPC/диковины/сундука игрока не выбрасывает в главное меню;
  2. «Подземелье» в меню и на клетке — только у VIP;
  3. профиль читается страницами, а не одной простынёй;
  4. сумка разделена на снаряжение / предметы / материалы / карман,
     а предмет открывается страницей книги;
  5. лавка — книга и её нет в главном меню;
  6. лавка лекаря доступна из меню только VIP;
  7. мировая карта рисует ряд локаций вдоль X горизонтально.

python3 tests/test_bot_ui.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                        create_async_engine)
    import aiosqlite  # noqa: F401
    from aiogram.utils.keyboard import InlineKeyboardBuilder  # noqa: F401
    from PIL import Image
except ImportError:
    print("⚠ Пропуск: нет sqlalchemy/aiogram/Pillow (pip install -r requirements.txt)")
    sys.exit(0)

from core.database import Base
from core.enums import CharacterClass, ItemRarity, ItemType, LocationType
from core.models import Character, InventoryItem, Item, Location, User

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


def datas(markup):
    """Все callback_data клавиатуры одним списком."""
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def texts(markup):
    return [b.text for row in markup.inline_keyboard for b in row]


async def make_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ── 1, 2: меню и клавиатуры ─────────────────────────────────

def test_menus():
    from bot.keyboards import inline as K

    print("\n— Главное меню —")
    plain = datas(K.main_menu_keyboard(has_character=True, is_vip=False))
    vip = datas(K.main_menu_keyboard(has_character=True, is_vip=True))
    check("dungeon_menu" not in plain, "у обычного игрока нет кнопки подземелья")
    check("dungeon_menu" in vip, "у VIP кнопка подземелья есть")
    check("shop" not in plain and "shop" not in vip,
          "лавка убрана из главного меню у всех")
    check("healer_shop" not in plain, "лавки лекаря нет у обычного игрока")
    check("healer_shop" in vip, "лавка лекаря доступна VIP из меню")
    check("profile" in plain and "inventory" in plain,
          "профиль и инвентарь остались на месте")

    print("\n— Клетка мира —")
    can = {d: True for d in ("n", "s", "e", "w")}
    cell_plain = datas(K.cell_movement_keyboard(can, is_vip=False))
    cell_vip = datas(K.cell_movement_keyboard(can, is_vip=True))
    check("dungeon_menu" not in cell_plain,
          "на клетке подземелья нет у обычного игрока")
    check("dungeon_menu" in cell_vip, "на клетке подземелье есть у VIP")
    check("main_menu" in cell_plain and "show_map" in cell_plain,
          "меню и карта на клетке никуда не делись")

    print("\n— Возврат к действию —")
    cont = datas(K.continue_keyboard())
    check(cont[0] == "back_to_cell",
          "первая кнопка после действия — «продолжить путь», а не меню")
    check("inspect" in cont, "рядом есть быстрый осмотр клетки")
    check("main_menu" in cont, "меню остаётся запасным выходом")
    with_extra = datas(K.continue_keyboard([("🛒 Торговать", "shop")]))
    check(with_extra[0] == "shop", "дополнительные действия идут первыми")


def test_handlers_use_continue():
    """Итоги мировых действий больше не ведут прямо в меню."""
    import inspect

    from bot.handlers import battle, location, world_extra

    print("\n— Экраны после действия —")
    for mod, name in ((battle, "battle"), (location, "location"),
                      (world_extra, "world_extra")):
        src = inspect.getsource(mod)
        uses = "continue_keyboard" in src
        check(uses, f"{name}: итоговые экраны используют «продолжить путь»")

    src = inspect.getsource(battle)
    check("main_menu_keyboard(has_character=True)" not in src,
          "battle: после боя игрока не выбрасывает в главное меню")

    src = inspect.getsource(location)
    check("reply_markup=continue_keyboard()" in src,
          "location: сундук возвращает к прогулке")


# ── 3: профиль-книга ────────────────────────────────────────

def test_profile_book():
    from bot.keyboards.inline import profile_book_keyboard
    from bot.utils.texts import PROFILE_PAGES, profile_page_text

    print("\n— Книга о герое —")
    total = len(PROFILE_PAGES)
    check(total >= 3, f"профиль разбит на страницы ({total})")

    char = Character(
        name="Тень", character_class=CharacterClass.WARRIOR, level=3,
        experience=120, gold=250, current_hp=40, current_mp=10,
        max_hp=60, max_mp=20, strength=12, agility=8, intelligence=5,
        endurance=9, luck=4,
    )
    char.location = None
    char.cell = None
    char.party = None

    stats = {"damage": 5, "defense": 3, "bonus": {"strength": 2},
             "gear": [], "max_hp": 60, "max_mp": 20}
    pages = [profile_page_text(char, i, None, stats, [], {})
             for i in range(total)]
    check(all(p.strip() for p in pages), "каждая страница непустая")
    longest = max(len(p) for p in pages)
    check(longest < 1024,
          f"страница влезает в подпись Telegram ({longest} символов)")
    check(len(set(pages)) == total, "страницы отличаются друг от друга")
    check("Характеристики" in pages[1] or "Сила" in pages[1],
          "второй разворот — характеристики")

    kb = datas(profile_book_keyboard(0, total, [t for _, t in PROFILE_PAGES]))
    check("profile_page:1" in kb, "есть переход на следующую страницу")
    check("main_menu" in kb, "из книги можно выйти в меню")
    last = datas(profile_book_keyboard(total - 1, total,
                                       [t for _, t in PROFILE_PAGES]))
    check(f"profile_page:{total}" not in last,
          "с последней страницы нет перехода в пустоту")


# ── 4: отделения сумки и книга предметов ────────────────────

async def test_inventory_sections():
    from bot.handlers.inventory import SECTIONS, split_sections
    from bot.keyboards.inline import (inventory_hub_keyboard,
                                      inventory_section_keyboard,
                                      item_book_keyboard)

    print("\n— Отделения сумки —")
    Session = await make_session()
    async with Session() as s:
        user = User(telegram_id=1, username="t")
        s.add(user)
        await s.flush()
        loc = Location(name="Погост", description="", location_type=LocationType.SAFE,
                       min_level=1, world_x=0, world_y=0)
        s.add(loc)
        await s.flush()
        char = Character(user_id=user.id, name="Тень",
                         character_class=CharacterClass.WARRIOR,
                         location_id=loc.id)
        s.add(char)

        sword = Item(name="Меч", description="острый", item_type=ItemType.WEAPON,
                     rarity=ItemRarity.COMMON, price=10)
        potion = Item(name="Зелье", description="лечит", item_type=ItemType.CONSUMABLE,
                      rarity=ItemRarity.COMMON, price=5)
        ore = Item(name="Руда", description="тяжёлая", item_type=ItemType.MATERIAL,
                   rarity=ItemRarity.COMMON, price=2)
        s.add_all([sword, potion, ore])
        await s.flush()

        s.add_all([
            InventoryItem(character_id=char.id, item_id=sword.id, is_equipped=True),
            InventoryItem(character_id=char.id, item_id=potion.id, quantity=3),
            InventoryItem(character_id=char.id, item_id=ore.id, quantity=7),
            InventoryItem(character_id=char.id, item_id=potion.id, in_stash=True),
        ])
        await s.commit()

        from bot.handlers.inventory import load_inventory
        items = await load_inventory(s, char.id)

    buckets = split_sections(items)
    check(len(buckets["gear"]) == 1, "надетое попало в «Снаряжение»")
    check(len(buckets["bag"]) == 1, "зелье попало в «Предметы»")
    check(len(buckets["mat"]) == 1, "руда лежит отдельно в «Материалах»")
    check(len(buckets["stash"]) == 1, "спрятанное попало в «Карман»")
    check(set(buckets) == set(SECTIONS), "все четыре отделения описаны")
    check(sum(len(v) for v in buckets.values()) == len(items),
          "ни одна вещь не потерялась при разделении")

    hub = datas(inventory_hub_keyboard(
        {k: len(v) for k, v in buckets.items()} | {"stash_cap": 5}))
    check(all(f"inv_sec:{k}:0" in hub for k in SECTIONS),
          "с главного экрана сумки открывается каждое отделение")

    lst = datas(inventory_section_keyboard(buckets["bag"], "bag", 0))
    check(any(d.startswith("inv_book:bag:") for d in lst),
          "из списка вещь открывается страницей книги")
    check("inventory" in lst, "из отделения можно вернуться к отделениям")

    book = datas(item_book_keyboard(1, "bag", 0, 3, can_equip=True))
    check("inv_book:bag:1" in book, "в книге предметов листаются страницы")
    check("inv_sec:bag:0" in book, "из книги можно вернуться к списку")


def test_item_book_text():
    from bot.utils.texts import item_book_text

    print("\n— Страница книги предметов —")
    item = Item(name="Ржавый меч", description="Клинок, видевший лучшие дни.",
                item_type=ItemType.WEAPON, rarity=ItemRarity.COMMON,
                price=20, bonus_damage=3, icon="🗡", level_requirement=1)
    text = item_book_text(item, 0, 5, price=20, stock=3, owned=1)
    check("Ржавый меч" in text, "в книге есть название вещи")
    check("страница <b>1</b> из <b>5</b>" in text, "видна нумерация страниц")
    check("Клинок, видевший" in text, "есть описание предмета")
    check("📜" in text, "есть кусочек истории/лора")
    check("⚔️ Урон +3" in text, "перечислены свойства")
    check("Цена: <b>20🪙</b>" in text and "осталось <b>3</b>" in text,
          "видна цена и остаток на прилавке")
    check(len(text) < 1024, f"страница влезает в подпись ({len(text)})")

    material = Item(name="Руда", description="Тяжёлый ком железа.",
                    item_type=ItemType.MATERIAL, rarity=ItemRarity.COMMON,
                    price=2, icon="🧱")
    mtext = item_book_text(material, 1, 2)
    check("Материал" in mtext, "у материала свой тип на странице")
    check("без бонусов" in mtext, "у материала честно сказано про бонусы")


# ── 7: мировая карта ────────────────────────────────────────

def test_world_map():
    from core.map_renderer import render_world_map, world_bounds

    print("\n— Мировая карта —")

    class LType:
        def __init__(self, v):
            self.value = v

    class Loc:
        def __init__(self, i, name, wx, wy, t="safe"):
            self.id, self.name = i, name
            self.world_x, self.world_y = wx, wy
            self.min_level = 1
            self.location_type = LType(t)

    # пять стартовых локаций стоят в ряд вдоль оси X
    locs = [Loc(i + 1, f"Локация {i}", i, 0) for i in range(5)]
    x0, y0, x1, y1 = world_bounds(locs, 10)
    check((x0, x1, y0, y1) == (0, 4, 0, 0),
          f"карта обрезана по занятой области, а не 10×10 ({x0},{y0}..{x1},{y1})")

    path = render_world_map(locs, {1, 2, 3}, 2, 10, "data/test_world_map.png")
    w, h = Image.open(path).size
    check(w > h, f"ряд локаций вдоль X рисуется горизонтально ({w}×{h})")
    check(w / h >= 4, f"пропорции соответствуют ряду из пяти локаций ({w}/{h})")

    # вертикальная цепочка должна получиться вертикальной
    vert = [Loc(i + 1, f"Локация {i}", 0, i) for i in range(5)]
    vpath = render_world_map(vert, {1}, 1, 10, "data/test_world_map_v.png")
    vw, vh = Image.open(vpath).size
    check(vh > vw, f"цепочка вдоль Y рисуется вертикально ({vw}×{vh})")

    for f in (path, vpath):
        try:
            os.remove(f)
        except OSError:
            pass


def test_admin_grid_axes():
    """Сетка админки должна класть world_x на колонки, а не на строки."""
    print("\n— Оси в админ-панели —")
    for tpl in ("admin/templates/editor_world.html",
                "admin/templates/players_map.html"):
        src = open(tpl, encoding="utf-8").read()
        i_y = src.find("{% for wy in grid_range %}")
        i_x = src.find("{% for wx in grid_range %}")
        check(0 <= i_y < i_x,
              f"{os.path.basename(tpl)}: строка сетки — это world_y")


async def main():
    test_menus()
    test_handlers_use_continue()
    test_profile_book()
    await test_inventory_sections()
    test_item_book_text()
    test_world_map()
    test_admin_grid_axes()

    print("\n" + ("=" * 46))
    if FAILED:
        print(f"❌ Провалено проверок: {len(FAILED)}")
        for f in FAILED:
            print("   ·", f)
        sys.exit(1)
    print("✅ Экраны бота в порядке")


if __name__ == "__main__":
    asyncio.run(main())
