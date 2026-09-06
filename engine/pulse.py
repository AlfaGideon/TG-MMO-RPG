"""🩸 Пульс героя: один экран вместо лестницы меню.

Идея 1.1 из IDEAS-new-2026.md. Никакого нового состояния не заводится:
собирается уже посчитанное — HP/MP, валюта, карма, активные задания,
события мира (катаклизм/босс/осада), фаза луны, дом и карта сокровищ.
Модуль — «витрина», поэтому его паритет с сервером не требуется:
сервер покажет тот же пульс в bot/handlers/character.py.
"""
import time

from engine import (cataclysm, currency, death, factions, homestead, karma,
                    lunar, merchant, quests, rules, siege, stash, worldboss)
from engine.models import Reply

TASKS_SHOWN = 3


def _minutes_left(until: float) -> str:
    left = max(0, int(float(until) - time.time()))
    mins = left // 60
    if mins >= 60:
        return f"{mins // 60}ч {mins % 60}м"
    return f"{mins}м"


def _event_lines(store, p):
    """Живые игровые события: катаклизм, босс, осада, луна, торговец."""
    lines = []
    if store is None:
        return lines

    for e in cataclysm.active(store):
        where = "весь мир" if int(e.get("loc", 0)) == cataclysm.GLOBAL else "здесь"
        lines.append(f"{cataclysm.title(e['kind'])} · {where} · "
                     f"ещё {_minutes_left(e['until'])}")
    boss = worldboss.active(store)
    if boss:
        loc_name = "?"
        try:
            from engine import data
            loc_name = data.LOCATIONS[int(boss["loc"])][0]
        except Exception:
            pass
        lines.append(f"{worldboss.title(boss['key'])} · {loc_name} · "
                     f"❤️ {boss['hp']}/{boss['max_hp']} · "
                     f"ещё {_minutes_left(boss['until'])}")
    for s in siege.active(store):
        from engine import factions as _f
        atk = _f.FACTIONS.get(siege.attacker_of(s), ("⚔️", "?"))
        place = "?"
        try:
            from engine import data
            place = data.LOCATIONS[int(s["loc"])][0]
        except Exception:
            pass
        lines.append(f"🔥 {atk[0]} {atk[1]} · {place} · "
                     f"ворота {s['hp']}/{s['max_hp']} · "
                     f"ещё {_minutes_left(s['until'])}")
    phase = lunar.phase_of(store)
    if phase:
        lines.append(f"{phase['name']} · {phase['desc']}")
    if merchant.at(store, p.loc):
        lines.append(f"🧳 Здесь стоит {merchant.MERCHANT_NAME}")
    return lines


def _task_lines(p, store=None):
    """Активные задания: до трёх, с прогрессом."""
    live = quests.active(p)
    if not live or store is None:
        return []
    rows = []
    for q in live[:TASKS_SHOWN]:
        f = quests.fields(q)
        mark = "✅" if quests.complete(p, q) else "▫️"
        rows.append(f"{mark} <b>{f['name']}</b>\n{quests.goal_line(p, q)}")
    more = len(live) - len(rows)
    if more > 0:
        rows.append(f"…и ещё {more} задание(я) — открой 📜 Дневник.")
    return rows


def _home_line(p):
    if not homestead.settled(p):
        return ""
    level = int(p.house_level or 0)
    title = homestead.LEVEL_TITLES.get(level, "🏠 Дом")
    where = homestead.home_loc(p)
    at = " · ты дома" if homestead.at_home(p) else f" · {where}"
    chest = f"{len(getattr(p, 'home', None) or [])}/{homestead.cap_of(p)}"
    return f"{title} ур. {level} · сундук {chest}{at}"


def pulse(p, store=None):
    """Карточка «что с героем и миром прямо сейчас»."""
    if not p.created_char:
        return Reply(alert="Сначала создай героя!")
    s = rules.stats(p, store)
    lines = [
        f"{data_id(p)}",
        f"💪 {s['strength']} · 🏃 {s['agility']} · 🧠 {s['intelligence']} · "
        f"🛡 {s['endurance']} · 🍀 {s['luck']}",
        f"⚔️ Урон +{s['damage']} · 🛡 Защита +{s['defense']}",
    ]
    hurt = death.note(p) if death.wounded(p) else ""
    if hurt:
        lines.append(hurt)
    lines += [
        "",
        f"❤️ {p.hp}/{s['max_hp']}  {rules.bar(p.hp, s['max_hp'])}",
        f"💙 {p.mp}/{s['max_mp']}  {rules.bar(p.mp, s['max_mp'], '🟦')}",
        f"⭐ {p.exp}/{rules.exp_needed(p.level)}",
    ]

    tasks = _task_lines(p, store)
    if tasks:
        lines.append("")
        lines.append("📜 <b>Задания</b>")
        lines += tasks

    event_lines = _event_lines(store, p)
    if event_lines:
        lines.append("")
        lines.append("🌍 <b>Мир</b>")
        lines += event_lines

    goal = _goal_lines(p)
    if goal:
        lines.append("")
        lines.append("🧭 <b>Цели</b>")
        lines += goal

    home_line = _home_line(p)
    if home_line:
        lines.append("")
        lines.append(home_line)

    lines.append("")
    lines.append(f"📍 Ты в: {_where(p)}")
    lines.append(f"🎒 Сумка {len(p.inventory)} · 🔒 {len(getattr(p, 'stash', None) or [])} · "
                 f"☠️ {p.kills}")

    rows = []
    boss = worldboss.active(store) if store is not None else None
    if boss:
        rows.append([("🏰 Идти к боссу", "boss")])
    rows += [
        [("📜 Задания", "quests"), ("🗺 Карта", "map")],
        [("🧭 В мир", "world"), ("🧙 Профиль", "profile")],
        [("🔕 Вести", "notify")],
        [("◀️ Меню", "menu")],
    ]
    return Reply(text="\n".join(lines), keyboard=rows)


def _where(p):
    from engine import data
    try:
        return f"{data.LOCATIONS[p.loc][0]} ({p.x},{p.y})"
    except Exception:
        return f"локация {p.loc} ({p.x},{p.y})"


def _goal_lines(p):
    """Личные цели: могила, карта сокровищ, фракция-глава, раны."""
    from engine import data
    out = []
    coords = getattr(p, "treasure_map_coord", "") or ""
    if coords:
        try:
            _, li, _, _, xi, _, _, yi = coords.split(":")
            li, xi, yi = int(li), int(xi), int(yi)
            out.append(f"📜 Карта сокровищ ведёт в «{data.LOCATIONS[li][0]}» "
                       f"({xi},{yi})")
        except Exception:
            out.append("📜 У тебя есть карта сокровищ")
    fence = getattr(p, "reputation", None) or {}
    max_rep = max((v for v in fence.values()), default=0)
    if max_rep:
        lead = [k for k, v in fence.items() if v == max_rep][0]
        from engine import factions
        name = factions.FACTIONS.get(lead, (None, lead))[1]
        out.append(f"🧭 Ты ближе всех к фракции «{name}» ({max_rep} очков)")
    return out


def data_id(p):
    from engine import data, stash as _stash
    crown = " 👑" if stash.is_vip(p) else ""
    cls = data.CLASSES[p.cls][0] if p.cls in data.CLASSES else p.cls
    return (f"🩸 <b>Пульс героя</b>{crown}\n"
            f"{cls} · ур. {p.level} · {currency.fmt(p)}\n"
            f"{karma.karma_line(p)}")
