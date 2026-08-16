"""Экраны прогресса героя: атлас монстров, титулы, перерождение.

Вынесено из `engine/game.py`, чтобы роутер не перевалил за 500 строк —
правило модульности проекта, его стережёт `tests/test_wiring.py`.

Логика механик лежит в `engine/bestiary.py`, `engine/titles.py` и
`engine/prestige.py`; здесь только сборка текста и кнопок.
"""
from engine import bestiary, prestige, titles
from engine.models import Reply

BACK_MENU = [("◀️ Меню", "menu")]


def bestiary_screen(p):
    """📖 Атлас монстров: побеждённые виды и бонус охотника."""
    text = bestiary.bestiary_card_text(p)
    total = sum(bestiary.get_bestiary(p).values())
    if total:
        text += (f"\n\n<i>Всего побед в атласе: {total}. Каждые "
                 f"{bestiary.KILLS_PER_STEP} побед над видом дают +1 % урона "
                 f"по нему (потолок +{bestiary.MAX_BONUS_PCT} %).</i>")
    return Reply(text=text, keyboard=[BACK_MENU])


def titles_screen(p):
    """🎖 Титулы: выбрать знак доблести из открытых."""
    unlocked = titles.get_unlocked_titles(p)
    lines = ["🎖 <b>Титулы</b>", ""]
    rows = []
    if not unlocked:
        lines.append("<i>Ты пока не заслужил ни одного титула.</i>")
        lines.append("")
        lines.append("<i>Титулы дают постоянную прибавку к статам.</i>")
    else:
        active = getattr(p, "active_title", "") or ""
        for name in unlocked:
            t = titles.TITLES_CATALOG.get(name)
            if not t:
                continue
            mark = " ✅" if name == active else ""
            lines.append(f"{t['icon']} <b>{name}</b> — {t['desc']}{mark}")
            if name != active:
                rows.append([(f"{t['icon']} Надеть", f"title:{name}")])
        if active:
            rows.append([("🚫 Снять титул", "title:none")])
    rows.append(BACK_MENU)
    return Reply(text="\n".join(lines), keyboard=rows)


def set_title(store, p, name):
    """Надеть или снять титул. Носить можно только открытый."""
    if not titles.set_active_title(p, name):
        return Reply(alert="Этот титул ещё не открыт.")
    store.save_player(p)
    r = titles_screen(p)
    r.alert = ("Титул снят." if name in ("none", "")
               else f"Титул надет: {name}")
    return r


def rebirth_screen(p):
    """♻️ Перерождение: цена и выгода ритуала."""
    ok, reason = prestige.can_rebirth(p)
    count = getattr(p, "rebirth_count", 0) or 0
    text = ("♻️ <b>Вечное Перерождение</b>\n\n"
            "<i>— Сбрось прожитое и вернись сильнее, чем был.</i>\n\n"
            f"🔥 Кругов пройдено: <b>{count}</b>\n"
            f"📈 Уровень: <b>{p.level}</b> "
            f"(нужен {prestige.REBIRTH_MIN_LEVEL}+)\n\n"
            "Уровень и опыт обнулятся, но базовые статы вырастут "
            "на <b>+10 %</b> навсегда.\n\n"
            + ("✅ " + reason if ok else "⛔️ " + reason))
    rows = [[("🔥 Совершить перерождение", "rebirthgo")]] if ok else []
    rows.append(BACK_MENU)
    return Reply(text=text, keyboard=rows)


def rebirth_do(store, p):
    """Провести ритуал перерождения."""
    res = prestige.perform_rebirth(p, store)
    if not res["ok"]:
        return Reply(alert=res["reason"])
    return Reply(text=f"<b>{res['title']}</b>\n\n{res['desc']}",
                 keyboard=[[("🧙 Профиль", "profile")], BACK_MENU])


def talents_screen(p):
    """⭐ Созвездия: зажечь звезду за очко таланта."""
    from engine import talents

    unlocked = talents.get_unlocked_talents(p)
    points = getattr(p, "talent_points", 0) or 0
    lines = ["⭐ <b>Звёздное древо</b>", "",
             f"Свободных очков: <b>{points}</b> "
             f"(по одному раз в {talents.LEVELS_PER_POINT} уровня)", ""]
    rows = []
    for key, star in talents.TALENT_STARS.items():
        lit = key in unlocked
        lines.append(f"{'🔆' if lit else '☆'} <b>{star['name']}</b> — {star['desc']}")
        if not lit and points > 0:
            rows.append([(f"Зажечь: {star['name']}", f"talentgo:{key}")])
    rows.append(BACK_MENU)
    return Reply(text="\n".join(lines), keyboard=rows)


def talent_unlock(store, p, key):
    """Зажечь звезду созвездия."""
    from engine import talents

    res = talents.unlock_talent(p, key)
    if not res["ok"]:
        return Reply(alert=res["reason"])
    store.save_player(p)
    r = talents_screen(p)
    r.alert = f"{res['star_name']}: {res['desc']}"
    return r


def subclass_screen(p):
    """🎓 Специализация: одна на героя, выбирается с порога уровня."""
    from engine import subclasses

    current = getattr(p, "subclass", "") or ""
    lines = ["🎓 <b>Специализация</b>", ""]
    rows = []
    if current and current in subclasses.SUBCLASSES:
        sub = subclasses.SUBCLASSES[current]
        lines += [f"Твой путь: <b>{sub['name']}</b>", f"<i>{sub['desc']}</i>", "",
                  "<i>Специализация выбирается один раз.</i>"]
    elif (p.level or 1) < subclasses.SUBCLASS_MIN_LEVEL:
        lines.append(f"<i>Путь открывается с {subclasses.SUBCLASS_MIN_LEVEL} "
                     f"уровня. Сейчас у тебя {p.level}.</i>")
    else:
        lines.append("Выбери путь — он останется с тобой навсегда:")
        lines.append("")
        for sub in subclasses.get_available_subclasses(p.cls):
            lines.append(f"<b>{sub['name']}</b> — <i>{sub['desc']}</i>")
            rows.append([(sub["name"], f"subgo:{sub['key']}")])
    rows.append(BACK_MENU)
    return Reply(text="\n".join(lines), keyboard=rows)


def subclass_choose(store, p, key):
    """Выбрать специализацию."""
    from engine import subclasses

    if getattr(p, "subclass", ""):
        return Reply(alert="Путь уже выбран — его не сменить.")
    res = subclasses.choose_subclass(p, key)
    if not res["ok"]:
        return Reply(alert=res["reason"])
    store.save_player(p)
    return Reply(text=f"🎓 <b>{res['subclass_name']}</b>\n\n{res['desc']}",
                 keyboard=[[("🧙 Профиль", "profile")], BACK_MENU])


def familiar_screen(p):
    """🐾 Фамильяр: спутник с пассивным бонусом."""
    from engine import currency, familiars

    lines = [familiars.familiar_card_text(p), ""]
    rows = []
    if not getattr(p, "familiar_type", ""):
        lines.append(f"👛 Кошелёк: <b>{currency.fmt(p)}</b>")
        lines.append("")
        for key, fam in familiars.FAMILIARS.items():
            lines.append(f"{fam['icon']} <b>{fam['name']}</b> — "
                         f"{currency.short(fam['cost'])}")
            lines.append(f"<i>{fam['desc']}</i>")
            if currency.can_afford(p, fam["cost"]):
                rows.append([(f"{fam['icon']} Приручить", f"famgo:{key}")])
    rows.append(BACK_MENU)
    return Reply(text="\n".join(lines), keyboard=rows)


def familiar_adopt(store, p, key):
    """Приручить спутника за бронзу."""
    from engine import currency, familiars

    fam = familiars.FAMILIARS.get(key)
    if fam is None:
        return Reply(alert="Такого спутника нет.")
    if getattr(p, "familiar_type", ""):
        return Reply(alert="У тебя уже есть спутник.")
    if not currency.spend(p, fam["cost"]):
        need = fam["cost"] - currency.total(p)
        return Reply(alert=f"Не хватает {currency.short(need)}.")
    familiars.set_familiar(p, key)
    store.save_player(p)
    r = familiar_screen(p)
    r.alert = f"🐾 Спутник приручён: {fam['name']}"
    return r


# ── мирные занятия ──────────────────────────────────────────
# Таблицы шансов общие с сервером (engine/gathering.py); здесь только
# применение результата к герою браузерного стека.

def fish(store, p):
    """🎣 Рыбалка на воде."""
    from engine import currency, gathering, rules

    kind, amount, exp = gathering.roll_fish()
    s = rules.stats(p, store)
    if kind == "heal":
        p.hp = min(s["max_hp"], p.hp + amount)
    elif kind == "mana":
        p.mp = min(s["max_mp"], p.mp + amount)
    elif kind == "gold":
        currency.earn(p, amount)
    rules.add_exp(p, exp)
    store.save_player(p)
    return Reply(text=f"🎣 <b>Рыбалка</b>\n\n{gathering.fish_text(kind, amount)}",
                 keyboard=[[("🎣 Ещё раз", "fish")], [("◀️ Назад", "look")]])


def herbs(store, p):
    """🌿 Травничество в лесу и на болоте."""
    from engine import gathering, items, rules

    name, desc = gathering.roll_herb()
    rules.add_exp(p, gathering.HERB_EXP)
    # В браузерном стеке сумка хранит индексы шаблонов, поэтому трава
    # ложится в реестр именных экземпляров как добыча занятия.
    items.create(store, 0, source="quest", owner=p.tg_id, detail=name)
    store.save_player(p)
    return Reply(text=f"🌿 <b>Травничество</b>\n\n{gathering.herb_text(name)}",
                 keyboard=[[("🌿 Ещё раз", "herbs")], [("◀️ Назад", "look")]])


def dig(store, p):
    """⛏ Раскопки: осколки скрижали и карта сокровищ."""
    from engine import gathering

    found, formed = gathering.fragment_progress(getattr(p, "relic_fragments", 0))
    p.relic_fragments = found
    coords = None
    if formed:
        import random as _rnd
        loc = _rnd.randint(1, max(1, len(__import__("engine.data", fromlist=["d"]).LOCATIONS) - 1))
        coords = (_rnd.randint(2, 7), _rnd.randint(2, 7))
        p.treasure_map_coord = f"loc:{loc}:x:{coords[0]}:y:{coords[1]}"
    store.save_player(p)
    return Reply(
        text="⛏ <b>Раскопки</b>\n\n"
             + gathering.fragment_text(found, formed, coords),
        keyboard=[[("⛏ Копать ещё", "dig")], [("◀️ Назад", "look")]])


# ── призрачный торговец и Зал Славы ─────────────────────────

def honor_grave(store, p):
    """🕯 Почтить память павшего: собрать прах предков."""
    from engine import death, spectral

    grave = death.at(store, p.loc, p.x, p.y, getattr(p, "floor", 0) or 0)
    if grave is None:
        return Reply(alert="Здесь нет могилы.")
    res = spectral.harvest_ash(p)
    store.save_player(p)
    return Reply(
        text=f"🕯 <b>Память павших</b>\n\nТы почтил память и собрал "
             f"<b>+{res['gained']}</b> 🕯 Праха предков.\n"
             f"Всего праха: <b>{res['total_ash']}</b> 🕯",
        keyboard=[[("👻 Призрачный торговец", "ghost")], [("◀️ Назад", "look")]])


def ghost_screen(p):
    """👻 Витрина призрачного торговца: платят прахом, не золотом."""
    from engine import spectral

    ash = spectral.ash_of(p)
    lines = ["👻 <b>Бродячий Призрак Павшего Торговца</b>", "",
             "<i>— Я помню звон монет... но здесь ценен лишь Прах предков 🕯.</i>",
             "", f"🕯 У тебя праха: <b>{ash}</b>", ""]
    rows = []
    for ware in spectral.get_spectral_wares():
        lines.append(f"{ware['name']} — <b>{ware['cost_ash']}</b> 🕯")
        lines.append(f"<i>{ware['desc']}</i>")
        if ash >= ware["cost_ash"]:
            rows.append([(f"Купить: {ware['name']}", f"ghostbuy:{ware['key']}")])
    rows.append([("◀️ Назад", "look")])
    return Reply(text="\n".join(lines), keyboard=rows)


def ghost_buy(store, p, key):
    """Покупка за прах предков."""
    from engine import death, rules, spectral

    ware = spectral.ware_by_key(key)
    if ware is None:
        return Reply(alert="Такого товара нет.")
    if not spectral.can_afford(p, key):
        need = ware["cost_ash"] - spectral.ash_of(p)
        return Reply(alert=f"Не хватает {need} 🕯 Праха предков.")

    p.soul_ash = spectral.ash_of(p) - ware["cost_ash"]
    if key == "spec_wound_heal":
        death.heal_wounds(p)
    elif key == "spec_ancestor_tear":
        p.max_mp += spectral.TEAR_MANA_BONUS
        p.mp = rules.stats(p, store)["max_mp"]
    store.save_player(p)
    return Reply(text=f"👻 <b>Призрачный обмен</b>\n\n{spectral.buy_text(ware, key)}",
                 keyboard=[[("👻 Ещё раз", "ghost")], [("◀️ Назад", "look")]])


def legends_screen(store):
    """🏆 Зал Славы: кто и что сделал первым на сервере."""
    from engine import legends

    return Reply(text=legends.hall_text(legends.all_records(store)),
                 keyboard=[BACK_MENU])


# ── теневая экономика: ломбард, вклады, чёрный рынок ────────
# Ставки общие с сервером (engine/shadowecon), хранилище своё:
# записи лежат в store.settings, а не в таблицах.

INVEST_STEPS = (100, 500, 2000)


def pawn_screen(store, p):
    """💍 Ломбард: свои займы и выкуп."""
    from engine import currency, itemui, rules, shadowecon as E

    E.sweep_loans(store)
    mine = E.active_loans(store, p.tg_id)
    lines = ["💍 <b>Ломбард Падальщиков</b>", "",
             "<i>— Вещь оставь, деньги забирай. Не выкупишь в срок — она моя.</i>",
             "", f"💰 Кошелёк: <b>{currency.fmt(p)}</b>", ""]
    rows = []
    if not mine:
        lines.append("<i>Твоих залогов здесь нет.</i>")
        lines.append("")
        lines.append("Заложить вещь можно из карточки предмета в сумке.")
    else:
        for loan in mine:
            name = rules.item(loan["idx"])["name"]
            lines.append(f"• <b>{name}</b> — выкуп {loan['buyback']}🟤")
            rows.append([(f"💰 Выкупить: {name} ({loan['buyback']}🟤)",
                          f"pawnback:{loan['id']}")])
    rows.append(BACK_MENU)
    return Reply(text="\n".join(lines), keyboard=rows)


def pawn_item(store, p, arg):
    """Заложить вещь из сумки: деньги сразу, вещь — ростовщику."""
    from engine import currency, itemui, rules, shadowecon as E, slots

    pos = int(arg)
    if pos < 0 or pos >= len(p.inventory):
        return Reply(alert="Предмет не найден.")
    if slots.is_equipped_at(p, pos):
        return Reply(alert="Сначала сними предмет.")

    idx = p.inventory[pos]
    loan = E.add_loan(store, p, idx, itemui.resale_of(idx))
    slots.take_at(p, pos)
    currency.earn(p, loan["loan"])
    store.save_player(p)
    store.save()
    return Reply(
        text=f"💍 <b>Заклад</b>\n\n{rules.item(idx)['name']} у ростовщика.\n\n"
             f"{E.loan_text(loan['loan'], loan['buyback'])}",
        keyboard=[[("💍 Мои займы", "pawn")], [("◀️ В сумку", "bag")]])


def pawn_redeem(store, p, arg):
    """Выкупить залог обратно."""
    from engine import currency, rules, shadowecon as E, slots

    loan = E.find_loan(store, arg)
    if loan is None or loan.get("redeemed"):
        return Reply(alert="Этот заём уже закрыт.")
    if int(loan.get("owner", 0)) != int(p.tg_id):
        return Reply(alert="Это чужой заём.")
    if loan.get("liquidated"):
        return Reply(alert="Срок вышел — вещь ушла на чёрный рынок.")
    if not currency.spend(p, loan["buyback"]):
        need = loan["buyback"] - currency.total(p)
        return Reply(alert=f"Не хватает {currency.short(need)}.")

    loan["redeemed"] = True
    slots.append_item(p, loan["idx"])
    store.save_player(p)
    store.save()
    r = pawn_screen(store, p)
    r.alert = f"Вещь выкуплена: {rules.item(loan['idx'])['name']}"
    return r


def invest_screen(store, p):
    """🏦 Вклад в лавку поселения."""
    from engine import currency, data, shadowecon as E

    summary = E.investment_summary(store, p.loc, p.tg_id)
    where = data.LOCATIONS[p.loc][0] if p.loc < len(data.LOCATIONS) else "поселение"
    lines = [f"🏦 <b>Вклад в лавку: {where}</b>", "",
             "<i>— Вложись в дело, и лавка отблагодарит долей с оборота.</i>", "",
             f"💰 Кошелёк: <b>{currency.fmt(p)}</b>",
             f"📦 Капитал лавки: <b>{summary['total_pool']}</b>🟤",
             f"🪙 Твой вклад: <b>{summary['my_invested']}</b>🟤 "
             f"(доля {summary['share_pct']}%)",
             f"💎 Получено дивидендов: <b>{summary['my_dividends']}</b>🟤", "",
             f"<i>Выплата — {int(E.DIVIDEND_RATE * 100)} % в сутки.</i>"]
    rows = [[(f"🏦 Вложить {step}🟤", f"investgo:{step}")]
            for step in INVEST_STEPS if currency.can_afford(p, step)]
    rows.append(BACK_MENU)
    return Reply(text="\n".join(lines), keyboard=rows)


def invest_do(store, p, arg):
    """Внести вклад фиксированной суммой."""
    from engine import currency, shadowecon as E

    amount = int(arg)
    if amount not in INVEST_STEPS:          # защита от подделанной кнопки
        return Reply(alert="Недопустимая сумма.")
    if not currency.spend(p, amount):
        return Reply(alert=f"Не хватает {currency.short(amount - currency.total(p))}.")
    row = E.invest(store, p, p.loc, amount)
    store.save_player(p)
    store.save()
    r = invest_screen(store, p)
    r.alert = f"Вложено {amount}🟤. Всего: {row['invested']}🟤."
    return r


def market_screen(store, p):
    """🕯 Чёрный рынок: изъятые за долги вещи."""
    from engine import currency, rules, shadowecon as E

    E.sweep_loans(store)
    wares = E.seized_wares(store)
    lines = ["🕯 <b>Чёрный рынок</b>", "",
             "<i>— Тише. Товар без имени, продавца ты не видел.</i>", "",
             f"💰 Кошелёк: <b>{currency.fmt(p)}</b>", ""]
    rows = []
    if not wares:
        lines.append("<i>Сегодня пусто. Загляни, когда чей-то срок выйдет.</i>")
    else:
        lines.append("🔒 <b>Изъято за долги</b>")
        for loan in wares:
            price = E.liquidated_price_for(loan["buyback"])
            name = rules.item(loan["idx"])["name"]
            lines.append(f"⚔️ {name} — <b>{price}</b>🟤")
            if currency.can_afford(p, price):
                rows.append([(f"Выкупить: {name} ({price}🟤)",
                              f"marketbuy:{loan['id']}")])
    rows.append(BACK_MENU)
    return Reply(text="\n".join(lines), keyboard=rows)


def market_buy(store, p, arg):
    """Выкупить изъятую вещь с рынка."""
    from engine import currency, rules, shadowecon as E, slots

    loan = E.find_loan(store, arg)
    if loan is None or loan.get("redeemed") or not loan.get("liquidated"):
        return Reply(alert="Этот товар уже продан.")
    price = E.liquidated_price_for(loan["buyback"])
    if not currency.spend(p, price):
        return Reply(alert=f"Не хватает {currency.short(price - currency.total(p))}.")

    # Вещь уходит покупателю и пропадает с витрины — дважды не продать.
    loan["redeemed"] = True
    slots.append_item(p, loan["idx"])
    store.save_player(p)
    store.save()
    return Reply(
        text=f"🕯 <b>Тайная сделка</b>\n\nТы выкупил "
             f"<b>{rules.item(loan['idx'])['name']}</b> за {price}🟤.\n\n"
             f"<i>Прежний владелец не сумел вернуть долг вовремя.</i>",
        keyboard=[[("🕯 Ещё раз", "market")], [("◀️ Меню", "menu")]])
