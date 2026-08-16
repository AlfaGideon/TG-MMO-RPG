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
