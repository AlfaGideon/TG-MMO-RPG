"""Теневая экономика: ломбард, вклады в лавки, чёрный рынок.

Три механики держатся вместе, потому что у них одна природа — **деньги и
время**: заём выдают под процент и на срок, вклад приносит долю в сутки,
изъятый залог перепродают с наценкой. Ставки лежали в трёх файлах
`core/` как «магические числа» (0.70, 1.15, 0.02, 1.35), причём часть из
них встречалась дважды. Здесь они собраны в одном месте и стали
**единственным источником правды** для обоих стеков.

Хранилище различается и остаётся своим у каждого стека: сервер держит
`PawnLoan` и `TownInvestment` в БД, браузерный стек — записи в
`store.settings` (таблиц там нет). Общими сделаны формулы и тексты.

Все суммы — в бронзе (см. `engine/currency`).
"""
import time

# ── ломбард ─────────────────────────────────────────────────
LOAN_SHARE = 0.70        # столько от оценки вещи выдают на руки
BUYBACK_MARKUP = 1.15    # выкуп дороже займа на 15 % — плата за услугу
LOAN_MIN = 20            # меньше этой суммы заём не имеет смысла
LOAN_DAYS = 3            # срок, после которого залог можно изъять

# ── вклады в городские лавки ────────────────────────────────
DIVIDEND_RATE = 0.02     # доля вклада, выплачиваемая за период
DIVIDEND_PERIOD_HOURS = 24

# ── чёрный рынок ────────────────────────────────────────────
# Перекуп продаёт изъятый залог дороже выкупа: иначе выгоднее было бы не
# платить по долгу и купить свою же вещь дешевле.
LIQUIDATED_MARKUP = 1.35

LOANS_KEY = "pawn_loans"        # ключи в store.settings браузерного стека
INVESTMENTS_KEY = "town_investments"


# ── формулы (общие для обоих стеков) ────────────────────────

def loan_for(item_value: int) -> int:
    """Сколько ростовщик даст за вещь такой оценки."""
    return max(LOAN_MIN, int(int(item_value or 0) * LOAN_SHARE))


def buyback_for(loan_value: int) -> int:
    """Во сколько обойдётся выкуп займа."""
    return int(int(loan_value or 0) * BUYBACK_MARKUP)


def liquidated_price_for(buyback_value: int) -> int:
    """Цена изъятого залога на витрине чёрного рынка."""
    return max(1, int(int(buyback_value or 0) * LIQUIDATED_MARKUP))


def dividend_for(invested: int) -> int:
    """Дивиденды с вклада за один расчётный период."""
    return int(int(invested or 0) * DIVIDEND_RATE)


def share_pct(mine: int, pool: int) -> int:
    """Доля вкладчика в общем капитале лавки, в процентах."""
    pool = int(pool or 0)
    return int((int(mine or 0) / pool) * 100) if pool > 0 else 0


def loan_expired(expires_ts, now=None) -> bool:
    """Вышел ли срок займа (для браузерного стека — по метке времени)."""
    if not expires_ts:
        return False
    return (now if now is not None else time.time()) > float(expires_ts)


# ── тексты (одинаковые в обоих стеках) ──────────────────────

def loan_text(loan_value: int, buyback: int, days: int = LOAN_DAYS) -> str:
    return (f"💍 Заложено за <b>{loan_value}</b>🟤.\n"
            f"Выкуп: <b>{buyback}</b>🟤, срок {days} дн.")


def not_enough_text(need: int) -> str:
    return f"Не хватает средств! Нужно {need}🟤."


# ── хранилище браузерного стека ─────────────────────────────
# Сервер для этого использует таблицы; здесь — списки в настройках Store.

def loans(store) -> list:
    lst = store.settings.get(LOANS_KEY)
    if not isinstance(lst, list):
        lst = []
        store.settings[LOANS_KEY] = lst
    return lst


def active_loans(store, tg_id=None) -> list:
    """Незакрытые займы: все или конкретного героя."""
    out = [l for l in loans(store)
           if not l.get("redeemed") and not l.get("liquidated")]
    if tg_id is not None:
        out = [l for l in out if int(l.get("owner", 0)) == int(tg_id)]
    return out


def add_loan(store, p, idx: int, item_value: int) -> dict:
    """Записать новый заём. Возвращает запись."""
    value = loan_for(item_value)
    loan = {
        "id": int(time.time() * 1000) % 10_000_000,
        "owner": int(getattr(p, "tg_id", 0) or 0),
        "idx": int(idx),
        "loan": value,
        "buyback": buyback_for(value),
        "expires": time.time() + LOAN_DAYS * 86400,
        "redeemed": False,
        "liquidated": False,
    }
    lst = loans(store)
    lst.append(loan)
    store.settings[LOANS_KEY] = lst
    return loan


def find_loan(store, loan_id):
    return next((l for l in loans(store) if int(l.get("id")) == int(loan_id)), None)


def sweep_loans(store) -> list:
    """Изъять просроченные залоги. Возвращает изъятые записи."""
    seized = []
    for loan in active_loans(store):
        if loan_expired(loan.get("expires")):
            loan["liquidated"] = True
            seized.append(loan)
    if seized:
        store.save()
    return seized


def seized_wares(store) -> list:
    """Изъятые вещи, доступные к выкупу на чёрном рынке."""
    return [l for l in loans(store)
            if l.get("liquidated") and not l.get("redeemed")]


def investments(store) -> dict:
    data = store.settings.get(INVESTMENTS_KEY)
    if not isinstance(data, dict):
        data = {}
        store.settings[INVESTMENTS_KEY] = data
    return data


def invest(store, p, loc: int, amount: int) -> dict:
    """Вложить сумму в лавку локации."""
    data = investments(store)
    key = f"{loc}:{int(getattr(p, 'tg_id', 0) or 0)}"
    row = data.get(key) or {"loc": int(loc), "owner": int(p.tg_id),
                            "invested": 0, "earned": 0}
    row["invested"] = int(row["invested"]) + int(amount)
    data[key] = row
    store.settings[INVESTMENTS_KEY] = data
    return row


def investment_summary(store, loc: int, tg_id: int) -> dict:
    """Свод по лавке: общий капитал, своя доля и полученные дивиденды."""
    data = investments(store)
    pool = sum(int(r["invested"]) for r in data.values()
               if int(r["loc"]) == int(loc))
    mine = data.get(f"{loc}:{tg_id}") or {"invested": 0, "earned": 0}
    return {
        "total_pool": pool,
        "my_invested": int(mine["invested"]),
        "my_dividends": int(mine["earned"]),
        "share_pct": share_pct(mine["invested"], pool),
    }


def pay_dividends(store) -> list:
    """Начислить дивиденды всем вкладчикам. Возвращает список выплат."""
    from engine import currency

    payouts = []
    data = investments(store)
    for row in data.values():
        amount = dividend_for(row["invested"])
        if amount <= 0:
            continue
        p = store.players.get(int(row["owner"]))
        if p is None:                      # вкладчик исчез — пропускаем
            continue
        currency.earn(p, amount)
        row["earned"] = int(row["earned"]) + amount
        store.save_player(p)
        payouts.append({"owner": int(row["owner"]), "amount": amount,
                        "loc": int(row["loc"])})
    if payouts:
        store.settings[INVESTMENTS_KEY] = data
        store.save()
    return payouts
