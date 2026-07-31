"""Деньги: разряды монет, кошелёк, премиум-валюта и её обмен.

Проверяем именно то, что легко сломать при правках экономики:

* разряды считаются от одной суммы в бронзе, а не от трёх счётчиков —
  иначе «99🥈 + 1🥈» даст «100🥈» вместо «1🥇»;
* награды и покупки идут через money.*, поэтому кошелёк не уходит в минус;
* премиум не смешивается с монетами и меняется только в одну сторону;
* панель показывает вкладку валют, а бот — экран кошелька.

python3 tests/test_money.py
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_js = types.ModuleType("js")
_js.document = types.SimpleNamespace(querySelector=lambda s: None,
                                     addEventListener=lambda *a: None)
sys.modules.setdefault("js", _js)
_ffi = types.ModuleType("pyodide.ffi")
_ffi.create_proxy = lambda f: f
_pyo = types.ModuleType("pyodide")
_pyo.ffi = _ffi
sys.modules.setdefault("pyodide", _pyo)
sys.modules.setdefault("pyodide.ffi", _ffi)

from engine import money  # noqa: E402
from engine.game import Game  # noqa: E402
from engine.storage import Store  # noqa: E402
from webapp.backend import MemoryStorage  # noqa: E402
from webapp.pages import economy as page_eco  # noqa: E402

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


class FakeBot:
    running = False
    me = None
    counters = {}


class Ctx:
    def __init__(self, store):
        self.store = store
        self.bot = FakeBot()
        self.log_lines = []
        self.state = {}
        self.actor = None


def hero(store, gold=0, gems=0):
    game = Game(store)
    p = store.player(1, "Гидеон")
    game.handle(p, "make:warrior")
    p.gold, p.premium = gold, gems
    store.save_player(p)
    return game, p


def test_denominations():
    print("\n— Разряды считаются от суммы в бронзе —")
    check(money.BRONZE_PER_SILVER == 100, "100🥉 = 1🥈")
    check(money.SILVER_PER_GOLD == 100, "100🥈 = 1🥇")
    check(money.BRONZE_PER_GOLD == 10_000, "10 000🥉 = 1🥇")
    check(money.split(0) == (0, 0, 0), "ноль — пустой кошелёк")
    check(money.split(99) == (0, 0, 99), "99 бронзы не даёт серебра")
    check(money.split(100) == (0, 1, 0), "сотая бронза сама стала серебром")
    check(money.split(9_999) == (0, 99, 99), "почти золотой")
    check(money.split(10_000) == (1, 0, 0), "сотое серебро стало золотым")
    check(money.split(12_345) == (1, 23, 45), "12 345 = 1🥇 23🥈 45🥉")
    check(money.total(1, 23, 45) == 12_345, "сборка обратно совпадает")
    # Ровно та ошибка, ради которой хранится одна сумма, а не три счётчика.
    check(money.split(money.total(0, 99, 0) + 100) == (1, 0, 0),
          "99🥈 + 1🥈 = 1🥇, а не 100🥈")


def test_formatting():
    print("\n— Запись сумм —")
    check(money.fmt(0) == "0🥉", f"ноль печатается: {money.fmt(0)}")
    check(money.fmt(45) == "45🥉", "младший разряд без старших")
    check(money.fmt(12_345) == "1🥇 23🥈 45🥉", money.fmt(12_345))
    check(money.fmt(10_000) == "1🥇", "нулевые хвосты не печатаются")
    check(money.fmt(10_045) == "1🥇 0🥈 45🥉",
          f"дырка в середине видна: {money.fmt(10_045)}")
    check(money.short(12_345) == "1🥇", "короткая запись — старший разряд")
    check(money.short(45) == "45🥉", "короткая запись мелочи")
    check(money.plus(250).startswith("+"), f"прибавка со знаком: {money.plus(250)}")
    check(money.fmt(-100).startswith("−"), f"минус виден: {money.fmt(-100)}")


def test_wallet():
    print("\n— Кошелёк не уходит в минус —")
    store = Store(MemoryStorage())
    _game, p = hero(store, gold=1_000)
    check(money.balance(p) == 1_000, "баланс читается")
    check(money.can_pay(p, 999) and not money.can_pay(p, 1_001), "хватает/не хватает")
    check(money.lack(p, 1_500) == 500, "недостача считается")
    check(money.pay(p, 400) and money.balance(p) == 600, "оплата списала ровно 400")
    check(not money.pay(p, 10_000), "непосильная покупка отклонена")
    check(money.balance(p) == 600, "и кошелёк при этом не тронут")
    check(money.earn(p, 400) == 400 and money.balance(p) == 1_000, "начисление")
    check(money.earn(p, -50) == 0 and money.balance(p) == 1_000,
          "отрицательная награда игнорируется")


def test_premium_is_separate():
    print("\n— Премиум отдельно от монет —")
    store = Store(MemoryStorage())
    _game, p = hero(store, gold=100, gems=10)
    check(money.premium(p) == 10, "кристаллы читаются")
    check(money.spend_premium(p, 4) and money.premium(p) == 6, "трата кристаллов")
    check(not money.spend_premium(p, 99), "нельзя уйти в минус кристаллами")
    check(money.premium(p) == 6, "счётчик не тронут отказом")
    check(money.balance(p) == 100, "монеты не изменились от операций с 💎")
    money.grant_premium(p, -100)
    check(money.premium(p) == 0, "списание ниже нуля упирается в ноль")


def test_exchange_one_way():
    print("\n— Обмен 💎 → монеты, но не обратно —")
    store = Store(MemoryStorage())
    _game, p = hero(store, gold=0, gems=10)
    rate = money.tune(store, "premium_rate")
    ok, msg = money.exchange(p, 2, store)
    check(ok, f"обмен прошёл: {msg}")
    check(money.balance(p) == 2 * rate, f"начислено по курсу {rate}")
    check(money.premium(p) == 8, "кристаллы списаны")
    ok, msg = money.exchange(p, 99, store)
    check(not ok and money.premium(p) == 8, f"нечем менять — отказ: {msg}")
    ok, _ = money.exchange(p, -5, store)
    check(not ok, "отрицательный обмен отклонён")
    check(not hasattr(money, "exchange_back"),
          "обратного обмена нет — донат не выводится")
    store.settings["premium_rate"] = 0
    ok, msg = money.exchange(p, 1, store)
    check(not ok, f"нулевой курс закрывает обмен: {msg}")


def test_settings():
    print("\n— Настройки валют —")
    store = Store(MemoryStorage())
    check(money.tune(store, "premium_rate") == money.PREMIUM_RATE, "курс по умолчанию")
    money.set_tunables(store, {"premium_rate": "500", "premium_welcome": "3"})
    check(money.tune(store, "premium_rate") == 500, "курс сохранён")
    check(money.tune(store, "premium_welcome") == 3, "стартовые кристаллы сохранены")
    money.set_tunables(store, {"premium_rate": ""})
    check(money.tune(store, "premium_rate") == money.PREMIUM_RATE,
          "пустое поле вернуло умолчание")
    money.set_tunables(store, {"premium_rate": "мусор"})
    check(money.tune(store, "premium_rate") == money.PREMIUM_RATE,
          "мусор не ломает настройку")


def test_welcome_bonus():
    print("\n— Стартовый кошелёк из настроек панели —")
    store = Store(MemoryStorage())
    store.settings["welcome_bonus"] = 25_000
    store.settings["premium_welcome"] = 5
    p = store.player(42, "Новичок")
    check(money.balance(p) == 25_000, f"новичок получил {money.fmt(p.gold)}")
    check(money.premium(p) == 5, "и стартовые кристаллы")
    p.gold = 10
    again = store.player(42)
    check(again.gold == 10, "существующему игроку бонус повторно не капает")


def test_rewards_and_purchases():
    print("\n— Награды и покупки идут через кошелёк —")
    store = Store(MemoryStorage())
    game, p = hero(store, gold=100_000)
    from engine import itemui, rules

    idx = 0
    price = rules.item(idx)["price"]
    before = money.balance(p)
    game.handle(p, f"buy:{idx}")
    check(money.balance(p) == before - price, f"покупка списала {money.fmt(price)}")
    check(idx in p.inventory, "предмет в сумке")

    p.gold = 0
    r = game.handle(p, f"buy:{idx}")
    check("не хватает" in (r.alert or "").lower(), f"без денег отказ: {r.alert}")
    check(money.balance(p) == 0, "кошелёк не ушёл в минус")

    pos = p.inventory.index(idx)
    resale = itemui.resale_of(idx)
    r = game.handle(p, f"sells:{pos}")
    check(money.balance(p) == resale, f"продажа дала {money.fmt(resale)}")


def test_screens():
    print("\n— Экраны кошелька и панели —")
    store = Store(MemoryStorage())
    game, p = hero(store, gold=12_345, gems=7)
    r = game.handle(p, "purse")
    check("Кошелёк" in r.text, "экран кошелька открывается")
    for icon in (money.GOLD_ICON, money.SILVER_ICON, money.BRONZE_ICON):
        check(icon in r.text, f"разряд {icon} показан")
    check(money.PREMIUM_ICON in r.text, "кристаллы показаны")
    acts = [a for row in r.keyboard for _, a in row]
    check(any(a.startswith("gemx:") for a in acts), "есть кнопки обмена")

    menu = game.menu(p)
    menu_acts = [a for row in menu.keyboard for _, a in row]
    check("purse" in menu_acts, "кошелёк доступен из главного меню")

    r = game.handle(p, "gemx:1")
    check(money.premium(p) == 6, f"обмен из бота сработал: {r.alert}")

    ctx = Ctx(store)
    ctx.state["eco_tab"] = "money"
    markup = page_eco.render(ctx)
    check("Деньги мира" in markup, "вкладка «Валюты» рисуется")
    check("money-save" in markup, "есть сохранение настроек валют")
    check("money-gem" in markup, "есть выдача кристаллов")
    check(money.fmt(p.gold) in markup, "кошелёк героя показан разрядами")

    prof = game.handle(p, "profile")
    check(money.fmt(p.gold) in prof.text, "профиль печатает разряды")


def main():
    for fn in (test_denominations, test_formatting, test_wallet,
               test_premium_is_separate, test_exchange_one_way, test_settings,
               test_welcome_bonus, test_rewards_and_purchases, test_screens):
        fn()

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
