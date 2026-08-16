"""Перенос в браузерный стек: ломбард, вклады, чёрный рынок.

Запуск: python3 tests/test_engine_shadowecon.py

Раздел 2 `IDEAS-100.md` (пункты 13, 14, 15). Три механики держатся
вместе: у них одна природа — деньги и время. Ставки (0.70, 1.15, 0.02,
1.35) лежали «магическими числами» в трёх файлах `core/`, часть из них
встречалась дважды; теперь они в `engine/shadowecon.py` и общие.

Хранилище остаётся разным: сервер — таблицы `PawnLoan`/`TownInvestment`,
браузерный стек — записи в `store.settings`.

Отдельно проверяется главное экономическое правило: выкуп дороже займа,
а изъятое перепродаётся ещё дороже — иначе выгодно не платить по долгу
и выкупить свою же вещь дешевле.
"""
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import currency, itemui, shadowecon as E, slots
from engine.game import Game
from engine.storage import Store
from webapp.backend import MemoryStorage

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


def _hero(store, game, tg_id, money=5000):
    p = store.player(tg_id, f"Герой{tg_id}")
    game.handle(p, "make:warrior")
    p.bronze, p.silver, p.gold = 0, 0, 0
    currency.earn(p, money)
    return p


def main():
    random.seed(8)
    store = Store(MemoryStorage())
    game = Game(store)

    print("\n— Формулы: заём, выкуп, перепродажа —")
    loan = E.loan_for(100)
    buyback = E.buyback_for(loan)
    resale = E.liquidated_price_for(buyback)
    check(loan < 100, f"дают меньше оценки: {loan} < 100")
    check(buyback > loan, f"выкуп дороже займа: {buyback} > {loan}")
    check(resale > buyback,
          f"перепродажа дороже выкупа: {resale} > {buyback} — "
          f"иначе выгодно не платить по долгу")
    check(E.loan_for(1) == E.LOAN_MIN, "мелочь оценивается по нижней границе")
    check(E.dividend_for(1000) == int(1000 * E.DIVIDEND_RATE),
          f"дивиденды {E.dividend_for(1000)}🟤 с 1000🟤")
    check(E.share_pct(250, 1000) == 25, "доля считается в процентах")
    check(E.share_pct(100, 0) == 0, "пустой капитал не делит на ноль")

    print("\n— Ломбард: заклад, выкуп, деньги —")
    p = _hero(store, game, 1)
    p.inventory.append(4)
    price = itemui.resale_of(4)
    before = currency.total(p)

    game.handle(p, "pawnput:0")
    l = E.active_loans(store, p.tg_id)[0]
    check(len(p.inventory) == 0, "вещь ушла ростовщику")
    check(currency.total(p) == before + l["loan"],
          f"деньги выданы: +{l['loan']}🟤")
    check(l["loan"] == E.loan_for(price), "сумма займа по общей формуле")

    poor = _hero(store, game, 2, money=0)
    poor.inventory.append(4)
    game.handle(poor, "pawnput:0")
    other_loan = E.active_loans(store, poor.tg_id)[0]
    r = game.handle(p, f"pawnback:{other_loan['id']}")
    check("чужой" in (r.alert or "").lower(), "чужой заём не выкупить")

    game.handle(p, f"pawnback:{l['id']}")
    check(len(p.inventory) == 1, "вещь вернулась в сумку")
    check(currency.total(p) == before + l["loan"] - l["buyback"],
          "списана цена выкупа")
    r = game.handle(p, f"pawnback:{l['id']}")
    check("закрыт" in (r.alert or "").lower(), "дважды выкупить нельзя")

    print("\n— Надетую вещь заложить нельзя —")
    armed = _hero(store, game, 3)
    armed.inventory.append(4)
    from engine import inventory as inv_mod
    inv_mod.equip(armed, 0, store)
    r = game.handle(armed, "pawnput:0")
    check("сними" in (r.alert or "").lower(), "экипировку сперва снимают")
    check(len(armed.inventory) == 1, "вещь осталась у героя")

    print("\n— Просрочка уходит на чёрный рынок —")
    debtor = _hero(store, game, 4)
    debtor.inventory.append(4)
    game.handle(debtor, "pawnput:0")
    overdue = E.active_loans(store, debtor.tg_id)[0]
    check(not E.seized_wares(store), "пока ничего не изъято")

    overdue["expires"] = time.time() - 1        # срок вышел
    seized = E.sweep_loans(store)
    check(any(x["id"] == overdue["id"] for x in seized), "залог изъят")
    check(E.seized_wares(store), "вещь появилась на витрине")

    r = game.handle(debtor, f"pawnback:{overdue['id']}")
    check("срок" in (r.alert or "").lower(), "просроченное уже не выкупить по-старому")

    buyer = _hero(store, game, 5, money=9000)
    market_price = E.liquidated_price_for(overdue["buyback"])
    money_before = currency.total(buyer)
    game.handle(buyer, f"marketbuy:{overdue['id']}")
    check(len(buyer.inventory) == 1, "вещь перешла покупателю")
    check(currency.total(buyer) == money_before - market_price,
          f"списано {market_price}🟤 по цене витрины")
    r = game.handle(buyer, f"marketbuy:{overdue['id']}")
    check("продан" in (r.alert or "").lower(), "дважды одну вещь не продать")
    check(not E.seized_wares(store), "витрина опустела")

    print("\n— Вклады и дивиденды —")
    investor = _hero(store, game, 6, money=3000)
    game.handle(investor, "investgo:500")
    summary = E.investment_summary(store, investor.loc, investor.tg_id)
    check(summary["my_invested"] == 500, "вклад записан")
    check(summary["share_pct"] == 100, "единственный вкладчик держит 100 %")

    r = game.handle(investor, "investgo:999")
    check("недопустимая" in (r.alert or "").lower(),
          "подделанная сумма отклонена")

    money_before = currency.total(investor)
    payouts = E.pay_dividends(store)
    expected = E.dividend_for(500)
    check(any(x["owner"] == investor.tg_id for x in payouts), "выплата начислена")
    check(currency.total(investor) == money_before + expected,
          f"дивиденды {expected}🟤 пришли в кошелёк")
    check(E.investment_summary(store, investor.loc, investor.tg_id)["my_dividends"]
          == expected, "выплата учтена в своде")

    print("\n— Экраны и меню —")
    datas = [d for row in game.menu(p).keyboard for _l, d in row]
    for cb in ("pawn", "invest", "market"):
        check(cb in datas, f"в меню есть «{cb}»")
    check("Ломбард" in game.handle(p, "pawn").text, "экран ломбарда открывается")
    check("Вклад" in game.handle(p, "invest").text, "экран вклада открывается")
    check("рынок" in game.handle(p, "market").text.lower(), "рынок открывается")

    print("\n— Ставки общие с сервером —")
    try:
        from core import blackmarket as c_bm
        from core import investments as c_inv
        from core import pawnshop as c_pawn
        check(c_pawn.E is E, "ломбард сервера берёт ставки отсюда")
        check(c_inv.DIVIDEND_RATE == E.DIVIDEND_RATE, "ставка дивидендов одна")
        check(c_bm.LIQUIDATED_MARKUP == E.LIQUIDATED_MARKUP,
              "наценка перекупа одна")
    except ImportError as e:
        check(True, f"серверный стек недоступен, пропуск ({e})")

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
