"""Аукцион игроков и скупщик-NPC.

Торговля «купить сразу»: продавец назначает цену, покупатель жмёт кнопку
и вещь меняет владельца вместе с летописью. Пока лот висит, предмет лежит
на витрине, а не в сумке. Скупщик Молчун выкупает вещь мгновенно за ~55 %
оценки и перевыставляет с наценкой, чтобы вещи не пропадали из мира.
"""
import secrets
import time

from engine import items, money
from engine.models import Reply

KEY = "auction"                 # список лотов в store.settings
COMMISSION = 0.05               # комиссия аукциона с продажи
NPC_BUY = 0.55                  # доля оценки, которую даёт скупщик
NPC_MARKUP = 1.35               # наценка скупщика при перевыставлении
LIFETIME = 24 * 60 * 60         # лот живёт сутки
MAX_LOTS = 5                    # своих активных лотов одновременно
NPC_NAME = "Скупщик Молчун"

# Готовые варианты цены: (подпись, множитель оценки)
PRICE_STEPS = [("💸 быстро", 0.7), ("🙂 по рынку", 1.0),
               ("💰 дорого", 1.4), ("🤑 очень дорого", 2.0)]


def _lots(store):
    lst = store.settings.get(KEY)
    if not isinstance(lst, list):
        lst = []
        store.settings[KEY] = lst
    return lst


def active(store, exclude=0):
    """Лоты, доступные к покупке. Попутно снимает просроченные."""
    expire(store)
    out = [l for l in _lots(store) if l.get("status") == "active"]
    if exclude:
        out = [l for l in out if int(l.get("seller") or 0) != int(exclude)]
    return sorted(out, key=lambda l: l.get("ts", 0), reverse=True)


def mine(store, tg_id):
    return [l for l in _lots(store) if l.get("status") == "active"
            and int(l.get("seller") or 0) == int(tg_id)]


def find(store, lot_id):
    for l in _lots(store):
        if str(l.get("id")) == str(lot_id):
            return l
    return None


def suggest(store, uid):
    """Оценка аукциона: цена экземпляра с учётом истории сделок."""
    inst = items.get(store, uid)
    return items.price(inst) if inst else 0


def price_options(store, uid):
    """Варианты цены для продавца: [(подпись, цена)]."""
    base = suggest(store, uid)
    return [(lbl, max(1, int(base * m))) for lbl, m in PRICE_STEPS]


# ── выставление и снятие ────────────────────────────────────

def list_item(store, p, uid, price):
    """Ставит именную вещь на витрину. (лот, сообщение)."""
    inst = items.get(store, uid)
    if inst is None:
        return None, "предмет не найден"
    if int(inst.get("owner") or 0) != int(p.tg_id):
        return None, "это не твоя вещь"
    if any(str(l.get("uid")) == str(uid) for l in active(store)):
        return None, "вещь уже на витрине"
    if len(mine(store, p.tg_id)) >= MAX_LOTS:
        return None, f"больше {MAX_LOTS} своих лотов нельзя"
    price = max(1, int(price))

    lot = {
        # Миллисекунды одни на двоих не делят: два лота за одну ms раньше
        # получали одинаковый id и снимались/покупались «по кругу».
        "id": f"L{int(time.time() * 1000) % 10 ** 9}{secrets.token_hex(2)}",
        "uid": str(uid), "seller": int(p.tg_id), "seller_name": p.name,
        "price": price, "ts": int(time.time()), "status": "active",
    }
    _lots(store).append(lot)
    idx = int(inst.get("idx", -1))
    if idx in p.inventory:                 # вещь уходит из сумки на витрину
        p.inventory.remove(idx)
        p.equipped = {s: i for s, i in p.equipped.items() if i != idx}
    inst["owner"] = 0
    items.record(store, inst, "listed", p.tg_id, price=price)
    store.save_player(p)
    return lot, f"выставлено за {money.fmt(price)}"


def cancel(store, p, lot_id):
    lot = find(store, lot_id)
    if lot is None or lot.get("status") != "active":
        return False, "лот не найден"
    if int(lot.get("seller") or 0) != int(p.tg_id):
        return False, "это не твой лот"
    lot["status"] = "cancelled"
    inst = items.get(store, lot["uid"])
    if inst:
        inst["owner"] = int(p.tg_id)
        items.record(store, inst, "expired", p.tg_id)
        p.inventory.append(int(inst.get("idx", 0)))
    store.save_player(p)
    return True, "лот снят, вещь вернулась в сумку"


def expire(store):
    """Возвращает продавцам лоты старше суток."""
    now = int(time.time())
    changed = 0
    for lot in _lots(store):
        if lot.get("status") != "active" or now - int(lot.get("ts") or now) < LIFETIME:
            continue
        lot["status"] = "expired"
        inst = items.get(store, lot["uid"])
        seller = store.players.get(int(lot.get("seller") or 0))
        if inst and seller is not None:
            inst["owner"] = seller.tg_id
            seller.inventory.append(int(inst.get("idx", 0)))
            items.record(store, inst, "expired", seller.tg_id)
        changed += 1
    if changed:
        store.save()
    return changed


# ── покупка ─────────────────────────────────────────────────

def buy(store, p, lot_id):
    """Покупка лота. (успех?, сообщение)."""
    lot = find(store, lot_id)
    if lot is None or lot.get("status") != "active":
        return False, "лот уже недоступен"
    if int(lot.get("seller") or 0) == int(p.tg_id):
        return False, "это твой собственный лот"
    price = int(lot.get("price") or 0)
    if not money.can_pay(p, price):
        return False, f"не хватает {money.fmt(money.lack(p, price))}"

    inst = items.get(store, lot["uid"])
    if inst is None:
        lot["status"] = "cancelled"
        return False, "предмет исчез с витрины"

    money.pay(p, price)
    p.inventory.append(int(inst.get("idx", 0)))
    items.transfer(store, inst, p.tg_id, "sold", price)
    lot["status"] = "sold"
    lot["buyer"] = int(p.tg_id)

    payout = max(1, int(price * (1 - COMMISSION)))
    seller = store.players.get(int(lot.get("seller") or 0))
    if seller is not None:
        from engine import adminops
        seller.gold += payout
        store.save_player(seller)
        adminops.queue(store, seller.tg_id,
                       f"🔁 Продано: <b>{items.title(inst)}</b> за {money.fmt(price)}\n"
                       f"Зачислено {money.fmt(payout)} (комиссия 5 %).")
    store.save_player(p)
    return True, f"куплено за {money.fmt(price)}"


def sell_to_npc(store, p, uid):
    """Скупщик берёт вещь мгновенно и перевыставляет её с наценкой."""
    inst = items.get(store, uid)
    if inst is None:
        return False, "предмет не найден"
    if int(inst.get("owner") or 0) != int(p.tg_id):
        return False, "это не твоя вещь"
    paid = max(1, int(items.price(inst) * NPC_BUY))
    money.earn(p, paid)
    idx = int(inst.get("idx", -1))
    if idx in p.inventory:
        p.inventory.remove(idx)
        p.equipped = {s: i for s, i in p.equipped.items() if i != idx}
    inst["owner"] = 0
    items.record(store, inst, "sold", p.tg_id, detail=NPC_NAME, price=paid)
    inst["trades"] = int(inst.get("trades") or 0) + 1

    _lots(store).append({
        "id": f"N{int(time.time() * 1000) % 10 ** 9}{secrets.token_hex(2)}",
        "uid": str(uid), "seller": 0, "seller_name": NPC_NAME,
        "price": max(1, int(items.price(inst) * NPC_MARKUP)),
        "ts": int(time.time()), "status": "active",
    })
    store.save_player(p)
    return True, f"{NPC_NAME} заплатил {money.fmt(paid)}"


# ── экраны бота ─────────────────────────────────────────────

def board(store, p, page=0):
    """Витрина: что сейчас продают другие."""
    from engine import itemui
    lots = active(store, exclude=p.tg_id)
    if not lots:
        return Reply(text=("🏛 <b>Аукцион</b>\n\n<i>Витрина пуста. "
                           "Выстави свою вещь — её увидят все игроки.</i>"),
                     keyboard=[[("📤 Мои лоты", "aucmine")],
                               [("◀️ Меню", "menu")]])
    entries, page = itemui.slice_page(lots, page)
    lines = ["🏛 <b>Аукцион</b>", f"👛 <b>{money.fmt(p.gold)}</b>", ""]
    rows, row = [], []
    for num, _pos, lot in entries:
        inst = items.get(store, lot["uid"])
        if inst is None:
            continue
        mark = "👛" if money.can_pay(p, lot["price"]) else "🚫"
        lines.append(f"{itemui.digit(num)} {inst['icon']} <b>{items.title(inst)}</b> "
                     f"· {mark} <b>{lot['price']}</b>")
        lines.append(f"     {items.tag(inst)} · продаёт {lot['seller_name']}")
        row.append((f"{itemui.digit(num)}{inst['icon']}", f"auclot:{lot['id']}"))
        if len(row) == itemui.PER_ROW:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows += itemui.pager(page, len(lots), "auc")
    rows.append([("📤 Мои лоты", "aucmine"), ("◀️ Меню", "menu")])
    lines.append("")
    lines.append("<i>Нажми номер — покажу вещь целиком, с её историей.</i>")
    return Reply(text="\n".join(lines), keyboard=rows)


def lot_card(store, p, lot_id):
    """Карточка лота: статы, происхождение и летопись вещи."""
    lot = find(store, lot_id)
    if lot is None or lot.get("status") != "active":
        return Reply(alert="Лот уже недоступен.")
    inst = items.get(store, lot["uid"])
    if inst is None:
        return Reply(alert="Предмет исчез.")
    from engine import itemui
    it = itemui.RARITY.get(inst.get("rarity"), ("⚪", inst.get("rarity", "")))
    log = items.history(inst)[-6:]
    body = "\n".join(log) if log else "<i>История пуста.</i>"
    text = (f"🏛 <b>Аукцион</b>\n\n"
            f"{inst['icon']} <b>{items.title(inst)}</b>\n"
            f"<code>{items.tag(inst)}</code>\n"
            f"{it[0]} {it[1]} · качество {inst.get('quality', 100)} %\n\n"
            f"{items.stats_line(inst)}\n\n"
            f"💵 Цена: <b>{money.fmt(lot['price'])}</b>\n"
            f"👛 У тебя: <b>{money.fmt(p.gold)}</b>\n"
            f"🧾 Продавец: {lot['seller_name']}\n\n"
            f"📖 <b>История вещи</b>\n{body}")
    rows = []
    if money.can_pay(p, lot["price"]) and int(lot.get("seller") or 0) != int(p.tg_id):
        rows.append([("🛒 Купить", f"aucbuy:{lot['id']}")])
    rows.append([("◀️ К витрине", "auc:0")])
    return Reply(text=text, keyboard=rows)


def my_lots(store, p):
    """Свои лоты и свои именные вещи, которые можно выставить."""
    from engine import itemui
    lots = mine(store, p.tg_id)
    lines = ["📤 <b>Мои лоты</b>", ""]
    rows = []
    for n, lot in enumerate(lots, 1):
        inst = items.get(store, lot["uid"])
        name = items.title(inst) if inst else "?"
        lines.append(f"{itemui.digit(n)} <b>{name}</b> · {money.fmt(lot['price'])}")
        rows.append([(f"❌ Снять {n}", f"aucoff:{lot['id']}")])
    if not lots:
        lines.append("<i>Активных лотов нет.</i>")
    lines += ["", f"<i>Одновременно можно держать до {MAX_LOTS} лотов.</i>"]

    own = items.owned_by(store, p.tg_id)[:itemui.PER_PAGE]
    if own:
        lines += ["", "<b>Можно выставить:</b>"]
        row = []
        for n, inst in enumerate(own, 1):
            lines.append(f"{itemui.digit(n)} {inst['icon']} {items.title(inst)} "
                         f"· оценка {money.fmt(items.price(inst))}")
            row.append((f"{itemui.digit(n)}{inst['icon']}", f"aucnew:{inst['uid']}"))
            if len(row) == itemui.PER_ROW:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
    rows.append([("🏛 Витрина", "auc:0"), ("◀️ Меню", "menu")])
    return Reply(text="\n".join(lines), keyboard=rows)


def sell_form(store, p, uid):
    """Выбор цены перед выставлением."""
    inst = items.get(store, uid)
    if inst is None:
        return Reply(alert="Предмет не найден.")
    lines = ["📢 <b>Выставить на аукцион</b>\n",
             f"{inst['icon']} <b>{items.title(inst)}</b>",
             f"<code>{items.tag(inst)}</code>",
             f"{items.stats_line(inst)}", "",
             f"Оценка аукциона: <b>{money.fmt(items.price(inst))}</b>", "",
             "<i>Выбери цену. Комиссия — 5 % с продажи.</i>"]
    rows = [[(f"{label} · {money.short(price)}", f"aucput:{uid}:{price}")]
            for label, price in price_options(store, uid)]
    rows.append([(f"🤝 Скупщику сразу · {money.short(int(items.price(inst) * NPC_BUY))}",
                  f"aucnpc:{uid}")])
    rows.append([("◀️ Назад", "aucmine")])
    return Reply(text="\n".join(lines), keyboard=rows)


def stats(store):
    """Сводка для панели: сколько лотов и на какую сумму наторговали."""
    lots = _lots(store)
    sold = [l for l in lots if l.get("status") == "sold"]
    return {"active": sum(1 for l in lots if l.get("status") == "active"),
            "sold": len(sold), "total": len(lots),
            "turnover": sum(int(l.get("price") or 0) for l in sold)}
