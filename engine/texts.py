"""Тексты интерфейса бота."""
from engine import data, hero, money, permissions, rules

WELCOME = (
    "🌑 <b>Теневые Земли</b>\n\n"
    "Тьма поглотила королевства, древние боги забыты, а выжившие прячутся "
    "за стенами полуразрушенных крепостей.\n\n"
    "<i>Создай героя и начни путь от изгнанника до легенды.</i>"
)

HELP = (
    "📜 <b>Помощь</b>\n\n"
    "• 🧭 Мир — перемещение по клеткам (8 направлений)\n"
    "• 🔍 Осмотреться — найти врагов, NPC и сундуки\n"
    "• 🧙 Профиль — статы и экипировка\n"
    "• 🎒 Инвентарь — надеть, снять, выпить, выбросить\n"
    "• 🏪 Лавка — торговец в Погосте\n"
    "• 🏕 Отдых — восстановить HP и MP\n"
    "• 📜 Задания — цели от жителей, ежедневные обновляются\n"
    "• 🤝 Отряд — <code>/invite Имя</code>, добыча делится на всех рядом\n"
    "• 🪦 Погиб — золото остаётся на месте гибели, вернись за ним\n\n"
    "Мир бесшовный: дойди до края локации, чтобы попасть в соседнюю.\n"
    "<i>Удачи в Теневых Землях...</i>"
)


def admin_panel(p):
    """Что показать админу в боте: ранг, права, как войти в панель."""
    return (
        "🛠 <b>Доступ администратора</b>\n\n"
        f"Ранг: <b>{permissions.rank_title(p.web_admin_role)}</b>\n"
        f"Логин: <code>{p.tg_id}</code>\n\n"
        "<b>Твои права:</b>\n"
        f"{permissions.summary(p)}\n\n"
        "<i>Вход в веб-панель — по логину и паролю. "
        "Нажми кнопку ниже, чтобы посмотреть пароль.</i>"
    )


def admin_password(p):
    return (
        "🔑 <b>Доступ в веб-панель</b>\n\n"
        f"Логин: <code>{p.tg_id}</code>\n"
        f"Пароль: <code>{p.web_admin_password}</code>\n\n"
        "<i>Нажми на пароль, чтобы скопировать. Никому его не передавай — "
        "администратор может сменить его в любой момент.</i>"
    )


def admin_granted(p):
    """Сообщение игроку в момент выдачи доступа."""
    return (
        "👑 <b>Тебе выдан доступ к админ-панели!</b>\n\n"
        f"Ранг: <b>{permissions.rank_title(p.web_admin_role)}</b>\n"
        f"Логин: <code>{p.tg_id}</code>\n"
        f"Пароль: <code>{p.web_admin_password}</code>\n\n"
        "<b>Что тебе доступно:</b>\n"
        f"{permissions.summary(p)}\n\n"
        "<i>Кнопка «🛠 Админка» появилась в главном меню бота.</i>"
    )


def admin_revoked():
    return ("🚫 <b>Доступ к админ-панели отозван.</b>\n\n"
            "<i>Кнопка «🛠 Админка» больше не доступна.</i>")


def roll_view(p, cls, rolled, magic):
    """Предпросмотр броска статов при создании героя."""
    title, desc, _base = data.CLASSES[cls]
    q = hero.quality(cls, rolled)
    left = int(getattr(p, "rolls", 0) or 0)
    lines = [f"<b>{title}</b>", f"<i>{desc}</i>", "",
             f"🎲 <b>Бросок судьбы</b> · {hero.verdict(q)} ({q} %)", ""]
    for key, label in (("strength", "💪 Сила"), ("agility", "🏃 Ловкость"),
                       ("intelligence", "🧠 Интеллект"),
                       ("endurance", "🛡 Выносливость"), ("luck", "🍀 Удача")):
        lines.append(f"{label}: <b>{rolled.get(key, 0)}</b>{hero.diff(cls, rolled, key)}")
    lines.append(f"❤️ HP: <b>{rolled.get('max_hp', 0)}</b>{hero.diff(cls, rolled, 'max_hp')}"
                 f"   💙 MP: <b>{rolled.get('max_mp', 0)}</b>{hero.diff(cls, rolled, 'max_mp')}")
    lines.append("")
    if magic:
        lines.append("✨ <b>Дар к магии</b>")
        lines += hero.magic_lines(magic)
    else:
        lines.append("🚫 <i>Магического дара нет — не всем он нужен.</i>")
    lines.append("")
    lines.append(f"<i>Осталось перекатов: {left}. Принятый бросок фиксируется.</i>")
    return "\n".join(lines)


def hero_created(p, cls):
    magic = hero.magic_lines(getattr(p, "magic", []))
    body = "\n".join(magic) if magic else "<i>Магического дара нет.</i>"
    return (f"✅ Герой <b>{p.name}</b> создан!\n\n"
            f"Класс: {data.CLASSES[cls][0]}\n"
            f"💪 {p.strength} · 🏃 {p.agility} · 🧠 {p.intelligence} · "
            f"🛡 {p.endurance} · 🍀 {p.luck}\n"
            f"❤️ {p.max_hp} HP · 💙 {p.max_mp} MP\n\n"
            f"✨ <b>Дар</b>\n{body}\n\n"
            f"Добро пожаловать в Теневые Земли, изгнанник.")


def profile(p, store=None):
    from engine import death, stash

    s = rules.stats(p, store)
    icon = data.CLASSES[p.cls][0].split()[0] if p.cls in data.CLASSES else "👤"
    eq = []
    for slot, idx in p.equipped.items():
        it = rules.item(idx)
        eq.append(f"{it['icon']} {it['name']}")
    magic = hero.magic_lines(getattr(p, "magic", []))
    magic_body = "\n".join(magic) if magic else "<i>дара нет</i>"
    crown = " 👑" if stash.is_vip(p) else ""
    kept = len(getattr(p, "stash", None) or [])
    hurt = f"\n{death.note(p)}" if death.wounded(p) else ""
    gems = f" · {money.premium(p)}{money.PREMIUM_ICON}" if money.premium(p) else ""
    return (
        f"{icon} <b>{p.name}</b>{crown} · ур. {p.level}\n"
        f"Класс: <code>{p.cls}</code> · 👛 {money.fmt(p.gold)}{gems}\n"
        f"🎒 Сумка: {len(p.inventory)} · 🔒 Карман: {kept}/{stash.capacity(p, store)}"
        f"{hurt}\n\n"
        f"❤️ HP {p.hp}/{s['max_hp']}\n{rules.bar(p.hp, s['max_hp'])}\n"
        f"💙 MP {p.mp}/{s['max_mp']}\n{rules.bar(p.mp, s['max_mp'], '🟦')}\n"
        f"⭐ Опыт {p.exp}/{rules.exp_needed(p.level)}\n\n"
        f"💪 Сила {s['strength']}   🏃 Ловкость {s['agility']}\n"
        f"🧠 Интеллект {s['intelligence']}   🛡 Выносливость {s['endurance']}\n"
        f"🍀 Удача {s['luck']}\n"
        f"⚔️ Урон +{s['damage']}   🛡 Защита +{s['defense']}\n\n"
        f"✨ <b>Магия</b>\n{magic_body}\n\n"
        f"🗡 Экипировка: {', '.join(eq) if eq else '—'}\n"
        f"☠️ Убито врагов: {p.kills}"
    )


def cell_view(p, cell, alarm="", others=()):
    """Описание клетки. `others` — другие герои, стоящие здесь же."""
    loc = data.LOCATIONS[p.loc]
    head = f"{alarm}\n\n" if alarm else ""
    company = ""
    if others:
        who = ", ".join(f"{q.name} (ур. {q.level})" for q in others[:4])
        more = f" и ещё {len(others) - 4}" if len(others) > 4 else ""
        company = f"\n\n🔵 <b>Здесь же:</b> {who}{more}"
    floor_line = (f"🏢 Этаж: <b>{getattr(p, 'floor', 0) + 1}</b>\n"
                  if getattr(p, 'floor', 0) else "")
    return (
        f"{head}🗺 <b>{loc[0]}</b>\n"
        f"{floor_line}"
        f"📍 [{cell.x},{cell.y}] · <i>{cell.name}</i>\n\n"
        f"{cell.desc}{company}\n\n"
        f"❤️ {p.hp}/{rules.stats(p)['max_hp']}  💙 {p.mp}  👛 {money.short(p.gold)}"
    )


def item_line(idx, equipped=False):
    it = rules.item(idx)
    mark = "✅ " if equipped else ""
    bon = ", ".join(f"{k} +{v}" for k, v in it["bonus"].items())
    return f"{mark}{it['icon']} {it['name']} <i>({bon})</i>"


def battle_view(p, st):
    m = data.MOBS[st["mob"]]
    queue = st.get("queue") or []
    waiting = ""
    if queue:
        names = ", ".join(
            data.MOBS[e["mob"] if isinstance(e, dict) else int(e)][0]
            for e in queue)
        waiting = f"\n⏳ Ждут своей очереди ({len(queue)}): <i>{names}</i>\n"
    return (
        f"⚔️ <b>Бой: {m[0]}</b> (ур. {m[2]})\n"
        f"<i>{m[1]}</i>\n\n"
        f"👾 {m[0]}: {max(0, st['mob_hp'])}/{m[3]}\n"
        f"{rules.bar(st['mob_hp'], m[3], '🟪')}\n"
        f"{waiting}\n"
        f"❤️ Ты: {p.hp}/{rules.stats(p)['max_hp']}\n"
        f"{rules.bar(p.hp, rules.stats(p)['max_hp'])}\n\n"
        + ("\n".join(st.get("log", [])[-4:]) if st.get("log") else "<i>Твой ход.</i>")
    )
