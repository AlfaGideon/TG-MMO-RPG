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
