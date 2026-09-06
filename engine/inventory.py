"""Инвентарь: сетка эмодзи-номеров, карточка предмета, экипировка.

В списке кнопки без подписей — только номер и иконка. Что скрыто за
номером, написано в тексте сообщения; подробности открываются нажатием.

Экипировка поддерживает именные экземпляры: при надевании в
`player.worn[слот]` пишется uid экземпляра (`items.resolve_owned`), и
боевые статы берутся от него через `rules.stats(p, store)`. Раньше
`worn` никто не заполнял, и в бою всегда считались статы шаблона —
паритет с серверным стеком восстановлен (AUDIT-BUGS.md, пункт B).
"""
from engine import combat, currency, durability, homestead, itemui, items, rules, slots, stash
from engine.models import Reply


def bag(p, page=0, store=None):
    if not p.inventory:
        return Reply(text=("🎒 <b>Инвентарь</b>\n\n<i>Сумка пуста.</i>\n\n"
                           "Загляни в 🏪 Лавку или обыщи сундуки в мире."),
                     keyboard=[[("🏪", "shop"), ("🧭", "world")],
                               [("◀️ Меню", "menu")]])

    worn_at = slots.equipped_positions(p)
    entries, page = itemui.slice_page(p.inventory, page)

    kept = len(getattr(p, "stash", None) or [])
    lines = [f"🎒 <b>Инвентарь</b> · 👛 {currency.fmt(p)} · "
             f"🔒 карман {kept}/{stash.capacity(p, store)}", ""]
    for num, _pos, idx in entries:
        note = ("<b>надето</b>" if _pos in worn_at
                else itemui.type_label(rules.item(idx)))
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
    equipped = slots.is_equipped_at(p, pos)
    page = pos // itemui.PER_PAGE

    extra = f"💰 Продать за <b>{currency.short(itemui.resale_of(idx))}</b>"
    if equipped:
        extra = "✅ <b>Надето на герое</b>\n\n" + extra
    if equipped and store is not None:
        uid = (getattr(p, "worn", None) or {}).get(it["type"])
        wearing = items.get(store, uid) if uid else None
        if wearing is not None:
            wear = durability.card_line(wearing)
            if wear:
                extra = f"{extra}\n\n{wear}"
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
    if not equipped:
        # Ломбард даёт меньше продажи, зато вещь можно выкупить обратно.
        rows.append([("💍 Заложить", f"pawnput:{pos}")])
    if stash.safe_here(p) and stash.free_slots(p, store) > 0:
        rows.append([("🔒 Убрать в карман", f"stput:{pos}")])
    if homestead.can_put(p):        # домой — только стоя у своих дверей
        rows.append([("🏠 Отнести в сундук", f"house:put:{pos}")])
    rows.append([("◀️ В сумку", f"bagp:{page}")])
    return Reply(text=text, keyboard=rows)


def equip(p, arg, store=None):
    pos = int(arg)
    if pos < 0 or pos >= len(p.inventory):
        return Reply(alert="Предмет не найден.")
    idx = p.inventory[pos]
    it = rules.item(idx)
    if not itemui.wearable(it):
        return Reply(alert="Это нельзя надеть.")
    # Запоминаем позицию и uid: слот указывает на КОНКРЕТНУЮ вещь, а статы
    # именного экземпляра должны работать в бою (rules.stats со store).
    uid = None
    if store is not None:
        from engine import durability, items
        inst = items.resolve_owned(store, p, idx)
        if inst is not None:
            if durability.broken(inst):
                return Reply(alert="🔩 Эта вещь сломана. Почини её в кузнице!")
            uid = inst["uid"]
    slots.equip_at(p, pos, it["type"], uid)
    r = card(p, pos, store)
    r.alert = f"Надето: {it['name']}"
    return r


def unequip(p, arg, store=None):
    pos = int(arg)
    if pos < 0 or pos >= len(p.inventory):
        return Reply(alert="Предмет не найден.")
    idx = p.inventory[pos]
    it = rules.item(idx)
    if not slots.is_equipped_at(p, pos):
        return Reply(alert="Предмет и так не надет.")
    slots.unequip_slot(p, it["type"])
    r = card(p, pos, store)
    r.alert = f"Снято: {it['name']}"
    return r


def use(p, arg, store=None):
    pos = int(arg)
    if pos < 0 or pos >= len(p.inventory):
        return Reply(alert="Предмет не найден.")
    idx = p.inventory[pos]
    it = rules.item(idx)
    if it["type"] != "consumable":
        return Reply(alert="Это не расходник.")
    from engine import karma
    s = rules.stats(p, store)
    got = []
    if "heal" in it["bonus"]:
        was = p.hp
        heal = it["bonus"]["heal"]
        # Благочестивые лечатся лучше — эффект порога кармы из karma.py.
        if karma.pious(p):
            heal = int(heal * (1 + karma.HEAL_BONUS))
        p.hp = min(s["max_hp"], p.hp + heal)
        got.append(f"❤️ +{p.hp - was}")
    if "mana" in it["bonus"]:
        was = p.mp
        p.mp = min(s["max_mp"], p.mp + it["bonus"]["mana"])
        got.append(f"💙 +{p.mp - was}")
    slots.take_at(p, pos)
    r = combat.view(p) if p.combat else bag(p, pos // itemui.PER_PAGE)
    r.alert = f"{it['name']}: {' · '.join(got) if got else 'использовано'}"
    return r


def sell(p, arg, store=None):
    pos = int(arg)
    if pos < 0 or pos >= len(p.inventory):
        return Reply(alert="Предмет не найден.")
    idx = slots.take_at(p, pos)      # снимет экипировку, только если ушла ОНА
    it = rules.item(idx)
    paid = itemui.resale_of(idx)
    currency.earn(p, paid)
    r = bag(p, pos // itemui.PER_PAGE, store)
    r.alert = f"Продано: {it['name']} за {currency.short(paid)}"
    return r


def toss(p, arg, store=None):
    pos = int(arg)
    if pos < 0 or pos >= len(p.inventory):
        return Reply(alert="Предмет не найден.")
    idx = slots.take_at(p, pos)      # снимет экипировку, только если ушла ОНА
    it = rules.item(idx)
    r = bag(p, pos // itemui.PER_PAGE, store)
    r.alert = f"Выброшено: {it['name']}"
    return r
