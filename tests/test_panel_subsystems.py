"""Pyodide-панель показывает подсистемы Раздела 2 (пункты № 71, 73–76).

python3 tests/test_panel_subsystems.py

Что было до этой партии: механики перенесли в `engine/`, игрок их видит в
боте, серверная админка — тоже (№ 61–66), а браузерная панель о них не
знала. Конкретно:

* `webapp/pages/players.py` не показывал `Player.karma_score`, хотя поле
  добавлено (`engine/models.py:46`) и влияет на лечение и урон Тьмы;
* `bestiary_kills_json` (`engine/models.py:50`) не показывался нигде;
* `relic_fragments` / `treasure_map_coord` (`engine/models.py:57-58`) —
  тайник существовал только в тексте у игрока;
* каталог `engine/familiars.FAMILIARS` в панели отсутствовал;
* ломбард, вклады и чёрный рынок (`engine/shadowecon.py`) — тоже.

Отдельная находка — **мёртвая механика**: `shadowecon.pay_dividends` в
браузерном стеке не вызывался ниоткуда (`grep -rn pay_dividends engine/
webapp/` находил только определение и тест), поэтому вклад никогда не
приносил дохода. Здесь проверяется ленивое начисление `accrue_dividends`.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Детерминизм (пункт № 5): панель рендерится на сгенерированном мире.
from _seed import pin  # noqa: E402

pin(116)

from engine import bestiary, familiars, karma  # noqa: E402
from engine import shadowecon as E  # noqa: E402
from engine.game import Game  # noqa: E402
from engine.storage import Store  # noqa: E402
from webapp.backend import MemoryStorage  # noqa: E402
from webapp.pages import content, dungeons, economy, players, world_map  # noqa: E402

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


class Ctx:
    """Минимальный контекст вместо App (как в tests/test_pages.py)."""

    def __init__(self):
        self.store = Store(MemoryStorage())
        self.state = {"loc": 0}
        self.log_lines = []


def build():
    ctx = Ctx()
    game = Game(ctx.store)

    hero = ctx.store.player(7, "Гидеон")
    game.handle(hero, "make:mage")
    hero.karma_score = -200                      # Осквернитель
    familiars.set_familiar(hero, "crow")
    for _ in range(23):                          # 23 победы → +2 %
        bestiary.record_kill(hero, "Помойная крыса")
    ctx.store.save_player(hero)

    digger = ctx.store.player(8, "Копатель")
    game.handle(digger, "make:warrior")
    digger.karma_score = 300                     # Благочестивый
    digger.relic_fragments = 5
    digger.treasure_map_coord = "loc:1:x:4:y:6"
    ctx.store.save_player(digger)

    E.add_loan(ctx.store, hero, 0, 200)
    E.invest(ctx.store, hero, 1, 1000)
    return ctx, hero, digger


def test_karma_in_players_page(ctx, hero, digger):
    print("\n№ 73 — карма в панели игроков")
    html = players.render(ctx)
    check("Карма" in html, "колонка «Карма» есть в таблице")
    check("💀" in html and "✨" in html,
          "значки Осквернителя и Благочестивого различаются")
    check("-200" in html, "число кармы выводится со знаком")

    form = players.edit_form(ctx, 7)
    check("pf_karma_score" in form, "в карточке есть поле правки кармы")
    icon, title, _ = karma.karma_status(hero)
    check(title in form, f"титул кармы взят из engine/karma: «{title}»")
    check(str(karma.PIOUS_KARMA) in form and str(karma.DEFILED_KARMA) in form,
          "пороги в подсказке — из кода, не переписаны руками")


def test_karma_edit_is_clamped(ctx):
    print("\n№ 73 — правка кармы не выходит за диапазон")
    from engine import adminops

    owner = ctx.store.player(7, "Гидеон")
    actor = None  # владелец панели (engine/adminops.require)

    adminops.set_fields(ctx.store, actor, 7, {"karma_score": 9999})
    check(owner.karma_score == karma.MAX_KARMA,
          f"перебор режется до MAX_KARMA ({karma.MAX_KARMA})")
    adminops.set_fields(ctx.store, actor, 7, {"karma_score": -9999})
    check(owner.karma_score == karma.MIN_KARMA,
          f"недобор режется до MIN_KARMA ({karma.MIN_KARMA})")
    adminops.set_fields(ctx.store, actor, 7, {"karma_score": "мусор"})
    check(owner.karma_score == karma.MIN_KARMA,
          "нечисловое значение игнорируется, а не роняет операцию")
    owner.karma_score = -200


def test_pets_tab(ctx):
    print("\n№ 74 — вкладка «Питомцы»")
    ctx.state["content_tab"] = "pets"
    html = content.render(ctx)
    for key, f in familiars.FAMILIARS.items():
        check(f["name"] in html, f"каталог показывает «{f['name']}»")
        check(str(f["cost"]) in html, f"цена {f['name']} — из engine/familiars")
    check("Гидеон" in html, "видно хозяина спутника")


def test_bestiary_tab(ctx):
    print("\n№ 76 — вкладка «Бестиарий»")
    ctx.state["content_tab"] = "bestiary"
    html = content.render(ctx)
    check("Помойная крыса" in html, "тварь из каталога в списке")
    pct = bestiary.slayer_pct(ctx.store.players[7], "Помойная крыса")
    check(f"+{pct}%" in html, f"бонус охотника совпадает с боем (+{pct} %)")
    check(str(bestiary.KILLS_PER_STEP) in html and str(bestiary.MAX_BONUS_PCT) in html,
          "пороги бестиария взяты из кода")


def test_archaeology(ctx):
    print("\n№ 75 — археология и метка тайника")
    ctx.state["content_tab"] = "dungeons"
    html = dungeons.render(ctx)
    check("Археология" in html, "блок археологии есть")
    check("Копатель" in html, "видно копателя")
    check("[4,6]" in html, "координаты тайника расшифрованы")

    ctx.state["loc"] = 1
    world = world_map.render(ctx)
    check("🏺" in world, "на карте мира стоит метка тайника")
    ctx.state["loc"] = 0


def test_shadow_economy_tab(ctx):
    print("\n№ 71 — вкладка «Теневая экономика»")
    ctx.state["eco_tab"] = "shadow"
    html = economy.render(ctx)
    check("Ломбард" in html, "блок ломбарда")
    check("Чёрный рынок" in html, "блок чёрного рынка")
    check("Вклады в лавки" in html, "блок вкладов")
    check(f"{int(E.LOAN_SHARE * 100)} %" in html,
          "доля займа в подсказке — из engine/shadowecon")
    check("1000🟤" in html, "капитал лавки посчитан")


def test_dividends_were_dead_now_accrue(ctx):
    print("\nМёртвая механика: дивиденды в браузерном стеке")
    store = ctx.store
    paid_before = E.investment_summary(store, 1, 7)["my_dividends"]
    check(paid_before == 0, "до начисления выплат не было")

    check(E.accrue_dividends(store) == [],
          "сразу после вклада платить нечего (период не прошёл)")

    # Отматываем отметку времени на три периода назад.
    store.settings[E.DIVIDEND_TS_KEY] = (
        time.time() - 3 * E.DIVIDEND_PERIOD_HOURS * 3600 - 10)
    payouts = E.accrue_dividends(store)
    check(len(payouts) == 3, f"догнаны все 3 пропущенных периода ({len(payouts)})")

    expected = 3 * E.dividend_for(1000)
    got = E.investment_summary(store, 1, 7)["my_dividends"]
    check(got == expected, f"начислено {got}🟤 = 3 × {E.dividend_for(1000)}🟤")

    check(E.accrue_dividends(store) == [],
          "повторный вызов ничего не платит (идемпотентность)")

    # Экран игрока начисляет сам — раньше он показывал ноль вечно.
    from engine import progress

    store.settings[E.DIVIDEND_TS_KEY] = (
        time.time() - E.DIVIDEND_PERIOD_HOURS * 3600 - 10)
    reply = progress.invest_screen(store, store.players[7])
    after = E.investment_summary(store, 1, 7)["my_dividends"]
    check(after == expected + E.dividend_for(1000),
          "заход на экран вклада начисляет накопившееся")
    check("Получено дивидендов" in reply.text, "экран показывает сумму")


def main():
    ctx, hero, digger = build()
    test_karma_in_players_page(ctx, hero, digger)
    test_karma_edit_is_clamped(ctx)
    test_pets_tab(ctx)
    test_bestiary_tab(ctx)
    test_archaeology(ctx)
    test_shadow_economy_tab(ctx)
    test_dividends_were_dead_now_accrue(ctx)

    print("\n" + "=" * 46)
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}")
        for f in FAILED:
            print("   -", f)
        return 1
    print("✅ Панель видит карму, питомцев, бестиарий, археологию и ломбард")
    return 0


if __name__ == "__main__":
    sys.exit(main())
