"""Экраны союзов и соперничества: арена, гильдии, наставничество.

Вынесено из `engine/progress.py`, чтобы файл не перевалил за 500 строк —
правило модульности проекта, его стережёт `tests/test_wiring.py`.

Правила механик лежат в `engine/arena.py` и `engine/guilds.py`;
здесь только сборка текста и кнопок.
"""
from engine.models import Reply

BACK_MENU = [("◀️ Меню", "menu")]



def arena_screen(store, p):
    """⚔️ Колизей Теней: бой со слепком другого героя."""
    from engine import arena

    arena.update_shadow(store, p)          # свой слепок всегда свежий
    foes = arena.opponents(store, p)
    rating = int(getattr(p, "arena_rating", 0) or arena.START_RATING)
    tokens = int(getattr(p, "gladiator_tokens", 0) or 0)

    lines = ["⚔️ <b>Колизей Теней</b>", "",
             "<i>— Здесь бродят астральные слепки других героев. "
             "Соперник не обязан быть в игре.</i>", "",
             f"🏆 Твой рейтинг: <b>{rating}</b>",
             f"🩸 Жетонов гладиатора: <b>{tokens}</b>", ""]
    rows = []
    if not foes:
        lines.append("<i>Других теней пока нет — ты первый на этой арене.</i>")
    else:
        lines.append("<b>Соперники:</b>")
        for foe in foes:
            lines.append(f"• {foe['name']} (ур. {foe['level']}) — "
                         f"рейтинг {foe['rating']}")
            rows.append([(f"⚔️ Вызвать: {foe['name']}",
                          f"arenago:{foe['owner']}")])
    rows.append(BACK_MENU)
    return Reply(text="\n".join(lines), keyboard=rows)


def arena_duel(store, p, arg):
    """Провести бой с выбранной тенью."""
    from engine import arena

    shadow = arena.find_shadow(store, arg)
    if shadow is None:
        return Reply(alert="Эта тень растворилась.")
    if int(shadow.get("owner", 0)) == int(p.tg_id):
        return Reply(alert="Со своей тенью драться незачем.")

    res = arena.duel(store, p, shadow)
    head = ("🏆 <b>Победа!</b>" if res["victory"] else "💀 <b>Поражение</b>")
    tail = "\n".join(res["log"][-4:])
    return Reply(
        text=f"{head}\n\nРаундов: {res['rounds']}\n\n{tail}\n\n"
             f"🩸 Жетонов: +{res['tokens']}\n"
             f"🏆 Рейтинг: {res['new_rating']} ({res['rating_change']:+d})",
        keyboard=[[("⚔️ Ещё бой", "arena")], [("◀️ Меню", "menu")]])


def guild_screen(store, p):
    """🏛 Гильдия: своя или список чужих."""
    from engine import currency, guilds

    guild, role = guilds.guild_of(store, p)
    rows = []
    if guild is not None:
        role_label = {"leader": "👑 глава"}.get(role, "🛡 участник")
        lines = [f"🏛 <b>{guild['name']}</b> — уровень {guild['level']}", "",
                 f"<i>{guild['desc']}</i>", "",
                 f"Твоя роль: <b>{role_label}</b>",
                 f"💰 Казна: <b>{guild['treasury']}</b>🟤",
                 f"👥 Участников: <b>{len(guild['members'])}</b>", "",
                 "<b>Состав:</b>"]
        for m in guild["members"][:15]:
            lines.append(f"• {m['name']}")
        for step in (100, 500):
            if currency.can_afford(p, step):
                rows.append([(f"💰 В казну {step}🟤", f"guilddep:{step}")])
    else:
        lines = ["🏛 <b>Гильдии</b>", "",
                 "<i>— В одиночку в этих землях долго не живут.</i>", "",
                 f"Основать свою: <b>{guilds.CREATE_COST}</b>🟤 "
                 f"(у тебя {currency.fmt(p)})", ""]
        others = guilds.all_guilds(store)
        if others:
            lines.append("<b>Уже существуют:</b>")
            for g in others[:8]:
                lines.append(f"• <b>{g['name']}</b> — ур. {g['level']}, "
                             f"участников {len(g['members'])}")
                rows.append([(f"🤝 Вступить: {g['name']}", f"guildjoin:{g['id']}")])
        else:
            lines.append("<i>Пока ни одной гильдии не основано. Стань первым.</i>")
        if currency.can_afford(p, guilds.CREATE_COST):
            rows.append([("🏛 Основать гильдию", "guildnew")])
    rows.append(BACK_MENU)
    return Reply(text="\n".join(lines), keyboard=rows)


def guild_create(store, p):
    """Основать гильдию: имя от героя, чтобы не требовать ввод текста."""
    from engine import currency, guilds

    if guilds.guild_of(store, p)[0] is not None:
        return Reply(alert="Ты уже состоишь в гильдии.")
    if not currency.spend(p, guilds.CREATE_COST):
        need = guilds.CREATE_COST - currency.total(p)
        return Reply(alert=f"Не хватает {currency.short(need)}.")
    res = guilds.create(store, p, f"Дом {p.name}")
    if not res["ok"]:
        currency.earn(p, guilds.CREATE_COST)     # возврат при отказе
        return Reply(alert=res["reason"])
    store.save_player(p)
    r = guild_screen(store, p)
    r.alert = "🏛 Гильдия основана! Ты её глава."
    return r


def guild_join(store, p, arg):
    res = __import__("engine.guilds", fromlist=["g"]).join(store, p, arg)
    if not res["ok"]:
        return Reply(alert=res["reason"])
    r = guild_screen(store, p)
    r.alert = f"🤝 Ты вступил в «{res['guild']['name']}»."
    return r


def guild_deposit(store, p, arg):
    """Взнос в казну гильдии."""
    from engine import currency, guilds

    amount = int(arg)
    if amount not in (100, 500):
        return Reply(alert="Недопустимая сумма.")
    guild, _role = guilds.guild_of(store, p)
    if guild is None:
        return Reply(alert="Ты не состоишь в гильдии.")
    if not currency.spend(p, amount):
        return Reply(alert=f"Не хватает {currency.short(amount - currency.total(p))}.")
    total = guilds.deposit(store, guild, amount)
    store.save_player(p)
    r = guild_screen(store, p)
    r.alert = f"💰 Внесено {amount}🟤. Казна: {total}🟤."
    return r


def mentor_screen(store, p):
    """🎓 Наставничество: найти учителя или считать очки чести."""
    from engine import guilds

    bonuses = guilds.mentor_bonuses(p)
    lines = ["🎓 <b>Наставничество</b>", "",
             "<i>— Ветеран ведёт новичка и получает Очки Чести.</i>", ""]
    rows = []
    if bonuses["has_mentor"]:
        mentor = store.players.get(int(p.mentor_id))
        lines.append(f"🧙 Твой наставник: <b>{mentor.name if mentor else '—'}</b>")
        lines.append(f"⭐ Бонус опыта: <b>+{bonuses['exp_bonus_pct']}%</b>")
    elif (p.level or 1) <= guilds.APPRENTICE_MAX_LEVEL:
        candidates = [q for q in store.players.values()
                      if q.tg_id != p.tg_id
                      and (q.level or 1) >= guilds.MENTOR_MIN_LEVEL]
        if candidates:
            lines.append("Выбери наставника — с ним опыт идёт быстрее:")
            for q in candidates[:5]:
                lines.append(f"• <b>{q.name}</b> (ур. {q.level})")
                rows.append([(f"🎓 В ученики к {q.name}", f"mentorgo:{q.tg_id}")])
        else:
            lines.append(f"<i>Опытных героев "
                         f"({guilds.MENTOR_MIN_LEVEL}+ уровень) пока нет.</i>")
    else:
        lines.append("<i>Ты уже не новичок — учеником стать нельзя.</i>")
        if (p.level or 1) >= guilds.MENTOR_MIN_LEVEL:
            lines.append("Зато можешь вести других: новички найдут тебя сами.")
    lines += ["", f"🏅 Очки Чести: <b>{bonuses['honor_points']}</b>"]
    rows.append(BACK_MENU)
    return Reply(text="\n".join(lines), keyboard=rows)


def mentor_bind(store, p, arg):
    """Взять наставника."""
    from engine import guilds

    mentor = store.players.get(int(arg))
    if mentor is None:
        return Reply(alert="Наставник не найден.")
    res = guilds.bind_mentor(store, p, mentor)
    if not res["ok"]:
        return Reply(alert=res["reason"])
    r = mentor_screen(store, p)
    r.alert = f"🎓 {res['mentor_name']} стал твоим наставником!"
    return r
