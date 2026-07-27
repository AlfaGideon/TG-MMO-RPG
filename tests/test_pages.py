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
    except Exception as e:
        check(False, f"форма клетки → {e}")

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
            check(m.count("class='c'") == 100, f"локация {i}: 100 клеток")
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
