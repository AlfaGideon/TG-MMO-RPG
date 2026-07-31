"""Инвентарь: сетка эмодзи-номеров, карточка предмета, экипировка.

В списке кнопки без подписей — только номер и иконка. Что скрыто за
номером, написано в тексте сообщения; подробности открываются нажатием.
"""
from engine import combat, itemui, rules, stash
from engine.models import Reply


def bag(p, page=0, store=None):
    if not p.inventory:
        return Reply(text=("🎒 <b>Инвентарь</b>\n\n<i>Сумка пуста.</i>\n\n"
                           "Загляни в 🏪 Лавку или обыщи сундуки в мире."),
                     keyboard=[[("🏪", "shop"), ("🧭", "world")],
                               [("◀️ Меню", "menu")]])

    worn = set(p.equipped.values())
    entries, page = itemui.slice_page(p.inventory, page)

    kept = len(getattr(p, "stash", None) or [])
    lines = [f"🎒 <b>Инвентарь</b> · 🪙 {p.gold} · "
             f"🔒 карман {kept}/{stash.capacity(p, store)}", ""]
    for num, _pos, idx in entries:
        note = "<b>надето</b>" if idx in worn else itemui.type_label(rules.item(idx))
        lines.append(itemui.line(num, idx, note))
    lines.append("")
    lines.append("<i>Нажми номер предмета — откроются подробности.</i>")

    lines.append("<i>🎒 Сумка теряется при гибели, 🔒 карман — нет.</i>")

    rows = itemui.grid(entries, "it")
    rows += itemui.pager(page, len(p.inventory), "bagp")
    rows.append([("🔒 Карман", "stash"), ("🏪", "shop"), ("🧙", "profile")])
    rows.append([("◀️ Меню", "menu")])
    return Reply(text="\n".join(lines), keyboard=rows)


def card(p, arg, store=None):
    """Карточка предмета из сумки: что это и что с ним можно сделать."""
    pos = int(arg)
    if pos < 0 or pos >= len(p.inventory):
        return Reply(alert="Предмет не найден.")
    idx = p.inventory[pos]
    it = rules.item(idx)
    equipped = p.equipped.get(it["type"]) == idx
    page = pos // itemui.PER_PAGE

    extra = f"💰 Продать за <b>{itemui.resale_of(idx)}</b> 🪙"
    if equipped:
        extra = "✅ <b>Надето на герое</b>\n\n" + extra
    text = "🎒 <b>Инвентарь</b>\n\n" + itemui.card(idx, extra)

    act = []
    if it["type"] == "consumable":
        act.append(("🧪 Использовать", f"use:{pos}"))
    elif equipped:
        act.append(("➖ Снять", f"off:{pos}"))
    elif itemui.wearable(it):
        act.append(("✅ Надеть", f"on:{pos}"))
    rows = [act] if act else []
    rows.append([("💰 Продать", f"sell:{pos}"), ("🗑 Выбросить", f"toss:{pos}")])
    if stash.safe_here(p) and stash.free_slots(p, store) > 0:
        rows.append([("🔒 Убрать в карман", f"stput:{pos}")])
    rows.append([("◀️ В сумку", f"bagp:{page}")])
    return Reply(text=text, keyboard=rows)


def equip(p, arg):
    pos = int(arg)
    if pos < 0 or pos >= len(p.inventory):
        return Reply(alert="Предмет не найден.")
    idx = p.inventory[pos]
    it = rules.item(idx)
    if not itemui.wearable(it):
        return Reply(alert="Это нельзя надеть.")
    p.equipped[it["type"]] = idx
    r = card(p, pos)
    r.alert = f"Надето: {it['name']}"
    return r


def unequip(p, arg):
    pos = int(arg)
    if pos < 0 or pos >= len(p.inventory):
        return Reply(alert="Предмет не найден.")
    idx = p.inventory[pos]
    it = rules.item(idx)
    if p.equipped.get(it["type"]) != idx:
        return Reply(alert="Предмет и так не надет.")
    p.equipped.pop(it["type"], None)
    r = card(p, pos)
    r.alert = f"Снято: {it['name']}"
    return r


def use(p, arg):
    pos = int(arg)
    if pos < 0 or pos >= len(p.inventory):
        return Reply(alert="Предмет не найден.")
    idx = p.inventory[pos]
    it = rules.item(idx)
    if it["type"] != "consumable":
        return Reply(alert="Это не расходник.")
    s = rules.stats(p)
    got = []
    if "heal" in it["bonus"]:
        was = p.hp
        p.hp = min(s["max_hp"], p.hp + it["bonus"]["heal"])
        got.append(f"❤️ +{p.hp - was}")
    if "mana" in it["bonus"]:
        was = p.mp
        p.mp = min(s["max_mp"], p.mp + it["bonus"]["mana"])
        got.append(f"💙 +{p.mp - was}")
    p.inventory.pop(pos)
    r = combat.view(p) if p.combat else bag(p, pos // itemui.PER_PAGE)
    r.alert = f"{it['name']}: {' · '.join(got) if got else 'использовано'}"
    return r


def sell(p, arg):
    pos = int(arg)
    if pos < 0 or pos >= len(p.inventory):
        return Reply(alert="Предмет не найден.")
    idx = p.inventory.pop(pos)
    it = rules.item(idx)
    if p.equipped.get(it["type"]) == idx:
        p.equipped.pop(it["type"])
    paid = itemui.resale_of(idx)
    p.gold += paid
    r = bag(p, pos // itemui.PER_PAGE)
    r.alert = f"Продано: {it['name']} за {paid} 🪙"
    return r


def toss(p, arg):
    pos = int(arg)
    if pos < 0 or pos >= len(p.inventory):
        return Reply(alert="Предмет не найден.")
    idx = p.inventory.pop(pos)
    it = rules.item(idx)
    if p.equipped.get(it["type"]) == idx:
        p.equipped.pop(it["type"])
    r = bag(p, pos // itemui.PER_PAGE)
    r.alert = f"Выброшено: {it['name']}"
    return r
