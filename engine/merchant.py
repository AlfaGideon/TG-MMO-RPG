"""Бродячий торговец: приходит в случайную локацию на несколько часов.

Правила общие для обоих стеков: торговец появляется при путешествии
(шанс `WANDER_CHANCE` на вход в локацию), торгует `LIFETIME` секунд,
продаёт диковинки с наценкой `MARKUP` и уходит. Состояние браузерного
стека живёт в `store.settings["merchant"]`; серверный стек хранит то же
в AppSetting (см. core/merchant.py).

Товары либо задаёт админ (панель), либо генерируются из каталога
`data.ITEMS`. Купленный товар уходит с витрины; раскупленное не
восстанавливается, пока торговец не уйдёт и не вернётся с новым добром.
"""
import random
import time

from engine import itemui, items, rules
from engine.models import Reply

KEY = "merchant"
MERCHANT_NAME = "🧳 Бродячий торговец"
MERCHANT_GREETING = ("Свежие диковинки! Дёшево — только для тех, кто "
                     "успел до заката.")
LIFETIME = 6 * 60 * 60       # сколько секунд торгует (совпадает с сервером)
WANDER_CHANCE = 0.12         # шанс встретить торговца при входе в локацию
MARKUP = 1.6                 # наценка к базовой цене товара
MAX_WARES = 12               # потолок товаров на витрине
PRICE_SPAN = (0.8, 2.0)      # разброс цены диковинки относительно базы


def _state(store):
    st = store.settings.get(KEY)
    if not isinstance(st, dict):
        st = {}
        store.settings[KEY] = st
    return st


def active(store):
    """Состояние торговца, если он сейчас торгует, иначе None."""
    st = _state(store)
    if not st.get("active"):
        return None
    if st.get("expires", 0) <= time.time():
        st["active"] = False
        store.save()
        return None
    return st


def at(store, loc):
    """Торговец в локации `loc`? Возвращает состояние или None."""
    st = active(store)
    if not st or int(st.get("location", -1)) != int(loc):
        return None
    return st


def _stock(store, st):
    """Наполнить витрину, если она пуста: случайные диковинки из каталога."""
    if st.get("items"):
        return
    from engine import data

    pool = list(range(len(data.ITEMS)))
    random.shuffle(pool)
    wares = []
    for idx in pool[:random.randint(3, 6)]:
        tpl = rules.item(idx)
        price = max(1, int(tpl["price"] * MARKUP *
                           random.uniform(*PRICE_SPAN)))
        qty = random.randint(3, 5) if tpl["type"] == "consumable" else 1
        wares.append({"item": idx, "price": price, "qty": qty})
    st["items"] = wares


def roll(store, p):
    """Шанс встретить торговца при входе героя в локацию.

    Если торговец уже торгует где-то — шанс, что он перебрался сюда
    (товары те же: это тот же торговец). Возвращает True, если он здесь.
    """
    st = _state(store)
    if not st.get("active"):
        if random.random() < WANDER_CHANCE:
            st.update(active=True, location=int(p.loc),
                      expires=time.time() + LIFETIME)
            _stock(store, st)
            store.save()
            return True
        return False
    if st.get("expires", 0) <= time.time():
        st["active"] = False
        store.save()
        return False
    if random.random() < WANDER_CHANCE * 0.5:
        st["location"] = int(p.loc)
        store.save()
        return True
    return False


def _wares(st):
    out = []
    for w in st.get("items") or []:
        if w.get("qty", 0) > 0:
            out.append(w)
    return out


def view(store, p, page=0):
    """Витрина торговца: страница товаров, как в лавке."""
    st = at(store, p.loc)
    if not st:
        return Reply(alert="Торговец уже ушёл.")
    wares = _wares(st)
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 0
    entries, page = itemui.slice_page([i for i in range(len(wares))], page)

    lines = [f"{MERCHANT_NAME}", f"<i>{MERCHANT_GREETING}</i>",
             f"🪙 <b>{p.gold}</b> · 🎒 {len(p.inventory)}", ""]
    if not wares:
        lines.append("<i>Витрина пуста — всё раскупили. Загляни позже.</i>")
    for num, _pos, pos in entries:
        w = wares[pos]
        tpl = rules.item(w["item"])
        mark = "🪙" if p.gold >= w["price"] else "🚫"
        qty = f" ×{w['qty']}" if w["qty"] > 1 else ""
        lines.append(itemui.line(num, w["item"], f"{mark} <b>{w['price']}</b>{qty}"))
    lines.append("<i>Нажми номер — покажу товар.</i>")

    rows = itemui.grid(entries, "mcard")
    rows += itemui.pager(page, len(wares), "merchant")
    rows.append([("◀️ В мир", "world")])
    return Reply(text="\n".join(lines), keyboard=rows)


def card(store, p, arg):
    """Карточка товара перед покупкой."""
    st = at(store, p.loc)
    if not st:
        return Reply(alert="Торговец уже ушёл.")
    wares = _wares(st)
    try:
        pos = int(arg)
    except (TypeError, ValueError):
        return Reply(alert="Такого товара нет.")
    if not 0 <= pos < len(wares):
        return Reply(alert="Такого товара нет.")
    w = wares[pos]
    price = int(w["price"])
    enough = p.gold >= price
    extra = (f"💵 Цена: <b>{price}</b> 🪙\n👛 У тебя: <b>{p.gold}</b> 🪙")
    if w["qty"] > 1:
        extra += f"\n📦 Осталось: {w['qty']} шт."
    if not enough:
        extra += f"\n\n🚫 <i>Не хватает {price - p.gold} 🪙</i>"
    text = f"{MERCHANT_NAME} · товар\n\n" + itemui.card(w["item"], extra)
    rows = []
    if enough:
        rows.append([("🛒 Купить", f"mbuy:{pos}")])
    rows.append([("◀️ К торговцу", "merchant")])
    return Reply(text=text, keyboard=rows)


def buy(store, p, arg):
    """Покупка диковинки: золото списывается, товар уходит с витрины."""
    st = at(store, p.loc)
    if not st:
        return Reply(alert="Торговец уже ушёл.")
    wares = _wares(st)
    try:
        pos = int(arg)
    except (TypeError, ValueError):
        return Reply(alert="Такого товара нет.")
    if not 0 <= pos < len(wares):
        return Reply(alert="Такого товара нет.")
    w = wares[pos]
    price = int(w["price"])
    if p.gold < price:
        return Reply(alert=f"Не хватает {price - p.gold} 🪙!")
    p.gold -= price
    w["qty"] -= 1
    p.inventory.append(w["item"])
    # Диковинки — именные: у снаряжения появляется экземпляр с историей.
    inst = items.create(store, w["item"], source="shop", owner=p.tg_id,
                        luck=p.luck, detail="бродячий торговец")
    store.save_player(p)
    r = card(store, p, arg)
    name = rules.item(w["item"])["name"]
    r.alert = f"Куплено: {name} за {price} 🪙"
    if inst:
        r.alert += f" · <code>{items.tag(inst)}</code>"
    return r
