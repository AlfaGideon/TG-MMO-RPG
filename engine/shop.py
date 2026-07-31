"""Лавка Варна: вкладки «Купить» и «Продать».

Кнопки списка — только эмодзи-номер и иконка товара. Что за товар и
почём, написано в тексте; карточка с кнопкой «Купить» / «Продать»
открывается нажатием номера.
"""
from engine import factions, itemui, rules
from engine.models import Reply

TITLE = "🏪 <b>Лавка Варна</b>"


def price_for(p, idx):
    """Цена товара для этого героя: репутация даёт скидку.

    Единая точка: список, карточка и покупка обязаны считать одинаково,
    иначе игрок увидит одну цену, а заплатит другую.
    """
    base = itemui.price_of(idx)
    return max(1, int(base * factions.price_mult(p)))


def _tabs(active):
    buy = ("🛒 Купить", "shop:0") if active != "buy" else ("• 🛒 Купить •", "noop")
    sell = ("💰 Продать", "sellbag:0") if active != "sell" else ("• 💰 Продать •", "noop")
    return [buy, sell]


def counter(p):
    return f"🪙 <b>{p.gold}</b> · 🎒 {len(p.inventory)}"


# ── покупка ─────────────────────────────────────────────────

def shop(p, page=0):
    goods = itemui.stock()
    entries, page = itemui.slice_page(goods, page)

    disc = factions.discount(p)
    lines = [TITLE, counter(p), ""]
    for num, _pos, idx in entries:
        price = price_for(p, idx)
        mark = "🪙" if p.gold >= price else "🚫"
        lines.append(itemui.line(num, idx, f"{mark} <b>{price}</b>"))
    lines.append("")
    if disc:
        lines.append(f"🧭 <i>Скидка за репутацию: −{int(disc * 100)}%</i>")
    lines.append("<i>Нажми номер товара — покажу, что это, и предложу купить.</i>")

    rows = itemui.grid(entries, "buyc")
    rows += itemui.pager(page, len(goods), "shop")
    rows.append(_tabs("buy"))
    rows.append([("🎒", "bag"), ("◀️ Меню", "menu")])
    return Reply(text="\n".join(lines), keyboard=rows)


def buy_card(p, arg):
    """Карточка товара перед покупкой."""
    idx = int(arg)
    goods = itemui.stock()
    if idx not in goods:
        return Reply(alert="Такого товара нет.")
    price = price_for(p, idx)
    enough = p.gold >= price
    page = goods.index(idx) // itemui.PER_PAGE

    base = itemui.price_of(idx)
    saved = f" <s>{base}</s>" if price < base else ""
    extra = (f"💵 Цена: <b>{price}</b> 🪙{saved}\n"
             f"👛 У тебя: <b>{p.gold}</b> 🪙")
    if not enough:
        extra += f"\n\n🚫 <i>Не хватает {price - p.gold} 🪙</i>"
    text = f"{TITLE} · товар\n\n" + itemui.card(idx, extra)

    rows = []
    if enough:
        rows.append([("🛒 Купить", f"buy:{idx}")])
    rows.append([("◀️ В лавку", f"shop:{page}")])
    return Reply(text=text, keyboard=rows)


def buy(p, arg):
    idx = int(arg)
    goods = itemui.stock()
    if idx not in goods:
        return Reply(alert="Такого товара нет.")
    price = price_for(p, idx)
    if p.gold < price:
        return Reply(alert=f"Не хватает {price - p.gold} 🪙!")
    p.gold -= price
    p.inventory.append(idx)
    r = buy_card(p, idx)
    r.alert = f"Куплено: {rules.item(idx)['name']} за {price} 🪙"
    return r


# ── продажа ─────────────────────────────────────────────────

def sell_list(p, page=0):
    """Вкладка продажи: сумка глазами торговца."""
    if not p.inventory:
        return Reply(text=f"{TITLE}\n\n<i>Тебе нечего продать — сумка пуста.</i>",
                     keyboard=[_tabs("sell"), [("◀️ Меню", "menu")]])

    worn = set(p.equipped.values())
    entries, page = itemui.slice_page(p.inventory, page)

    lines = [TITLE + " · скупка", counter(p), ""]
    for num, _pos, idx in entries:
        note = f"💰 <b>{itemui.resale_of(idx)}</b>"
        if idx in worn:
            note += " · надето"
        lines.append(itemui.line(num, idx, note))
    lines.append("")
    lines.append("<i>Варн даёт половину цены. Нажми номер, чтобы продать.</i>")

    rows = itemui.grid(entries, "sellc")
    rows += itemui.pager(page, len(p.inventory), "sellbag")
    rows.append(_tabs("sell"))
    rows.append([("🎒", "bag"), ("◀️ Меню", "menu")])
    return Reply(text="\n".join(lines), keyboard=rows)


def sell_card(p, arg):
    """Карточка своего предмета перед продажей."""
    pos = int(arg)
    if pos < 0 or pos >= len(p.inventory):
        return Reply(alert="Предмет не найден.")
    idx = p.inventory[pos]
    it = rules.item(idx)
    page = pos // itemui.PER_PAGE

    extra = (f"💰 Варн даёт: <b>{itemui.resale_of(idx)}</b> 🪙\n"
             f"👛 Станет: <b>{p.gold + itemui.resale_of(idx)}</b> 🪙")
    if p.equipped.get(it["type"]) == idx:
        extra = "⚠️ <i>Предмет надет — при продаже снимется.</i>\n\n" + extra
    text = f"{TITLE} · скупка\n\n" + itemui.card(idx, extra)

    return Reply(text=text, keyboard=[
        [("💰 Продать", f"sells:{pos}")],
        [("◀️ К скупке", f"sellbag:{page}")]])


def sell_here(p, arg):
    """Продажа из лавки: остаёмся в скупке, а не уходим в сумку."""
    pos = int(arg)
    if pos < 0 or pos >= len(p.inventory):
        return Reply(alert="Предмет не найден.")
    idx = p.inventory.pop(pos)
    it = rules.item(idx)
    if p.equipped.get(it["type"]) == idx:
        p.equipped.pop(it["type"])
    paid = itemui.resale_of(idx)
    p.gold += paid
    r = sell_list(p, pos // itemui.PER_PAGE)
    r.alert = f"Продано: {it['name']} за {paid} 🪙"
    return r
