"""Инвентарь: показ сумки, экипировка, использование, продажа."""
from engine import combat, rules, texts
from engine.models import Reply


def bag(p):
    if not p.inventory:
        return Reply(text="🎒 <b>Инвентарь</b>\n\nСумка пуста.",
                     keyboard=[[("◀️ Меню", "menu")]])
    rows, seen = [], {}
    for slot, idx in p.equipped.items():
        seen[idx] = slot
    lines = ["🎒 <b>Инвентарь</b>\n"]
    for pos, idx in enumerate(p.inventory):
        it = rules.item(idx)
        lines.append(texts.item_line(idx, idx in seen))
        rows.append([(f"{it['icon']} {it['name']}", f"it:{pos}")])
    rows.append([("◀️ Меню", "menu")])
    return Reply(text="\n".join(lines), keyboard=rows[:12])


def card(p, arg):
    pos = int(arg)
    if pos >= len(p.inventory):
        return Reply(alert="Предмет не найден.")
    idx = p.inventory[pos]
    it = rules.item(idx)
    rows = []
    if it["type"] == "consumable":
        rows.append([("🧪 Использовать", f"use:{pos}")])
    elif p.equipped.get(it["type"]) == idx:
        rows.append([("➖ Снять", f"off:{pos}")])
    else:
        rows.append([("✅ Надеть", f"on:{pos}")])
    rows.append([("💰 Продать", f"sell:{pos}"), ("🗑 Выбросить", f"toss:{pos}")])
    rows.append([("◀️ Назад", "bag")])
    bon = "\n".join(f"• {k} +{v}" for k, v in it["bonus"].items()) or "—"
    return Reply(text=(f"{it['icon']} <b>{it['name']}</b>\n"
                       f"<i>{it['type']} · {it['rarity']}</i>\n\n{bon}\n\n"
                       f"Цена продажи: {it['price'] // 2} 🪙"), keyboard=rows)


def equip(p, arg):
    idx = p.inventory[int(arg)]
    it = rules.item(idx)
    if it["type"] not in rules.SLOTS:
        return Reply(alert="Это нельзя надеть.")
    p.equipped[it["type"]] = idx
    r = bag(p)
    r.alert = f"Надето: {it['name']}"
    return r


def unequip(p, arg):
    idx = p.inventory[int(arg)]
    it = rules.item(idx)
    p.equipped.pop(it["type"], None)
    return bag(p)


def use(p, arg):
    pos = int(arg)
    idx = p.inventory[pos]
    it = rules.item(idx)
    s = rules.stats(p)
    if "heal" in it["bonus"]:
        p.hp = min(s["max_hp"], p.hp + it["bonus"]["heal"])
    if "mana" in it["bonus"]:
        p.mp = min(s["max_mp"], p.mp + it["bonus"]["mana"])
    p.inventory.pop(pos)
    r = combat.view(p) if p.combat else bag(p)
    r.alert = f"Использовано: {it['name']}"
    return r


def sell(p, arg):
    pos = int(arg)
    idx = p.inventory.pop(pos)
    it = rules.item(idx)
    if p.equipped.get(it["type"]) == idx:
        p.equipped.pop(it["type"])
    p.gold += it["price"] // 2
    r = bag(p)
    r.alert = f"Продано за {it['price'] // 2} 🪙"
    return r


def toss(p, arg):
    idx = p.inventory.pop(int(arg))
    it = rules.item(idx)
    if p.equipped.get(it["type"]) == idx:
        p.equipped.pop(it["type"])
    return bag(p)
