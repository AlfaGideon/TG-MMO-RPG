"""Проверка рендера страниц админки без браузера: python3 tests/test_pages.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.game import Game
from engine.storage import Store
from webapp.backend import MemoryStorage
from webapp.pages import bot, content, dashboard, players, settings, world

FAILED = []


class FakeBot:
    running = False
    me = None
    counters = {"updates": 0, "sent": 0, "errors": 0}


class Ctx:
    """Минимальный контекст вместо App."""
    def __init__(self):
        self.store = Store(MemoryStorage())
        self.bot = FakeBot()
        self.log_lines = [("12:00:00", "sys", "тест")]
        self.state = {"loc": 0}


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


def main():
    ctx = Ctx()
    game = Game(ctx.store)
    p = ctx.store.player(7, "Гидеон")
    game.handle(p, "make:mage")
    p.inventory.extend([0, 8])
    ctx.store.save_player(p)

    print("\n— Страницы —")
    for mod in (dashboard, bot, players, world, content, settings):
        try:
            markup = mod.render(ctx)
            ok = len(markup) > 200 and "<div class=\"card\">" in markup
            check(ok, f"{mod.TITLE} ({len(markup)} симв.)")
        except Exception as e:
            check(False, f"{mod.TITLE} → {type(e).__name__}: {e}")

    print("\n— Модальные формы —")
    try:
        f = players.edit_form(ctx, 7)
        check("pf_name" in f and "Гидеон" in f, "форма игрока")
    except Exception as e:
        check(False, f"форма игрока → {e}")
    try:
        f = world.cell_form(ctx, "0:5:5")
        check("cf_name" in f and "cf_mob" in f, "форма клетки")
        check("cell-close" in f, "у клетки есть кнопка закрытия дока")
        empty = world.cell_form(ctx, "")
        check("dock-empty" in empty, "без выбора док показывает подсказку")
    except Exception as e:
        check(False, f"форма клетки → {e}")
    try:
        f = world.cataclysm_form(ctx, "wildfire")
        check("cata-strike" in f and "cata_loc" in f, "форма катаклизма")
    except Exception as e:
        check(False, f"форма катаклизма → {e}")

    print("\n— Сетка мира создаёт, а не переселяет —")
    try:
        f = world.grid_place_form(ctx, 7, 7)
        check("world-loc-add" in f, "пустая клетка ведёт к созданию локации")
        check("grid_loc_idx" not in f, "нет выбора из существующих локаций")
        check('data-arg="7:7"' in f, "координаты клика вшиты в кнопку")
        check("loc_name" in f and "loc_type" in f, "поля новой локации на месте")
    except Exception as e:
        check(False, f"форма пустой клетки → {e}")
    try:
        f = world.grid_edit_form(ctx, 0, 0, 0)
        check("world-loc-edit" in f, "занятая клетка даёт правку свойств")
        check("world-grid-remove" in f, "и снятие с сетки")
    except Exception as e:
        check(False, f"форма занятой клетки → {e}")

    print("\n— Правка существующей локации —")
    try:
        f = world.loc_edit_form(ctx, 1)
        from engine import data as D
        check(D.LOCATIONS[1][0] in f, "имя локации подставлено")
        check(f"value=\"{D.LOCATIONS[1][3]}\"" in f, "мин. уровень подставлен")
        check("world-loc-save" in f and "world-loc-del" in f,
              "есть сохранение и удаление")
        check("loc_wx" not in f, "координаты не правятся тут — только drag&drop")
    except Exception as e:
        check(False, f"форма правки локации → {e}")
    markup = world.render(ctx)
    check("world-loc-edit" in markup, "в списке локаций есть кнопка правки")

    print("\n— Вкладки мира —")
    for tab in ("map", "grid", "cataclysms", "dungeons"):
        ctx.state["world_tab"] = tab
        try:
            m = world.render(ctx)
            check(len(m) > 200, f"вкладка {tab} ({len(m)} симв.)")
        except Exception as e:
            check(False, f"вкладка {tab} → {type(e).__name__}: {e}")
    ctx.state["world_tab"] = "map"

    print("\n— Выбор локации: стрелки вместо кнопок с названиями —")
    from webapp.pages import world_map
    ctx.state["world_tab"] = "map"
    ctx.state["loc"] = 0
    m = world.render(ctx)
    check("locnav" in m, "крест стрелок нарисован")
    near, here = world_map.neighbours(ctx, 0)
    check(here is not None, "локация 0 стоит на сетке мира")
    check(near["east"] is not None, "у неё есть сосед на востоке")
    check(f"data-arg='{near['east']}'" in m, "стрелка ведёт к соседу по сетке")
    check(near["west"] is None and "— нет —" in m,
          "без соседа стрелка гаснет, а не исчезает")
    # Кисть и туман войны убраны: они не работали и мешали правке клеток.
    for gone in ("data-brush", "paintBrush", "fogPlayerSelect", "Туман войны"):
        check(gone not in m, f"убрано: {gone}")
    check("locMapGrid" in m, "сетка карты на месте")
    check("cf_name" not in m or "cellDock" in m, "редактор клетки живёт в доке")

    print("\n— Экранирование —")
    evil = ctx.store.player(8, "<script>alert(1)</script>")
    ctx.store.save_player(evil)
    markup = players.render(ctx)
    check("<script>alert" not in markup and "&lt;script&gt;" in markup, "XSS в имени экранирован")

    print("\n— Все локации мира —")
    for i in range(5):
        ctx.state["loc"] = i
        try:
            m = world.render(ctx)
            check(m.count("class='c'") + m.count("class='c picked'") == 100,
                  f"локация {i}: 100 клеток")
        except Exception as e:
            check(False, f"локация {i} → {e}")

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
