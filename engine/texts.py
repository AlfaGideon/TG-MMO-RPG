"""Тексты интерфейса бота."""
from engine import data, rules

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
    "• 🏕 Отдых — восстановить HP и MP\n\n"
    "Мир бесшовный: дойди до края локации, чтобы попасть в соседнюю.\n"
    "<i>Удачи в Теневых Землях...</i>"
)


def profile(p):
    s = rules.stats(p)
    icon = data.CLASSES[p.cls][0].split()[0] if p.cls in data.CLASSES else "👤"
    eq = []
    for slot, idx in p.equipped.items():
        it = rules.item(idx)
        eq.append(f"{it['icon']} {it['name']}")
    return (
        f"{icon} <b>{p.name}</b> · ур. {p.level}\n"
        f"Класс: <code>{p.cls}</code> · Золото: <code>{p.gold}</code> 🪙\n\n"
        f"❤️ HP {p.hp}/{s['max_hp']}\n{rules.bar(p.hp, s['max_hp'])}\n"
        f"💙 MP {p.mp}/{s['max_mp']}\n{rules.bar(p.mp, s['max_mp'], '🟦')}\n"
        f"⭐ Опыт {p.exp}/{rules.exp_needed(p.level)}\n\n"
        f"💪 Сила {s['strength']}   🏃 Ловкость {s['agility']}\n"
        f"🧠 Интеллект {s['intelligence']}   🛡 Выносливость {s['endurance']}\n"
        f"🍀 Удача {s['luck']}\n"
        f"⚔️ Урон +{s['damage']}   🛡 Защита +{s['defense']}\n\n"
        f"🗡 Экипировка: {', '.join(eq) if eq else '—'}\n"
        f"☠️ Убито врагов: {p.kills}"
    )


def cell_view(p, cell):
    loc = data.LOCATIONS[p.loc]
    return (
        f"🗺 <b>{loc[0]}</b>\n"
        f"📍 [{cell.x},{cell.y}] · <i>{cell.name}</i>\n\n"
        f"{cell.desc}\n\n"
        f"❤️ {p.hp}/{rules.stats(p)['max_hp']}  💙 {p.mp}  🪙 {p.gold}"
    )


def item_line(idx, equipped=False):
    it = rules.item(idx)
    mark = "✅ " if equipped else ""
    bon = ", ".join(f"{k} +{v}" for k, v in it["bonus"].items())
    return f"{mark}{it['icon']} {it['name']} <i>({bon})</i>"


def battle_view(p, st):
    m = data.MOBS[st["mob"]]
    return (
        f"⚔️ <b>Бой: {m[0]}</b> (ур. {m[2]})\n"
        f"<i>{m[1]}</i>\n\n"
        f"👾 {m[0]}: {max(0, st['mob_hp'])}/{m[3]}\n"
        f"{rules.bar(st['mob_hp'], m[3], '🟪')}\n\n"
        f"❤️ Ты: {p.hp}/{rules.stats(p)['max_hp']}\n"
        f"{rules.bar(p.hp, rules.stats(p)['max_hp'])}\n\n"
        + ("\n".join(st.get("log", [])[-3:]) if st.get("log") else "<i>Твой ход.</i>")
    )
