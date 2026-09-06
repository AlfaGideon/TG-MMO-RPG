"""🔕 Экран центра вестей (браузерный стек).

Вынесено из `engine/progress.py`, чтобы тот не разъедался сверх лимита
500 строк. Правила и дефолты — в `engine/notify.py`; здесь только
сборка текста и кнопок.
"""
from engine import notify
from engine.models import Reply


def notify_screen(p):
    """🔕 Центр вестей: что слать, что выключить и когда молчать."""
    prefs = notify.of(p)
    lines = ["🔕 <b>Центр вестей</b>", "",
             "Личные напоминания приходят, когда сочтут нужным. "
             "Здесь ты решаешь, что не должно отвлекать.", ""]
    rows = []
    for key, label in notify.CHANNELS:
        state = "✅ вкл" if prefs.get(key) else "⛔ выкл"
        lines.append(f"{label}: <b>{state}</b>")
        rows.append([(f"{label}: {state}", f"notify:{key}")])
    quiet = prefs.get("quiet_enabled")
    q_state = "🌙 вкл" if quiet else "☀️ выкл"
    lines += [
        "",
        f"Тихие часы ({prefs['quiet_start']}–{prefs['quiet_end']}): "
        f"<b>{q_state}</b>",
        "<i>В это время личные вести не приходят; глобальные анонсы "
        "о порталах остаются рассылкой.</i>",
    ]
    rows.append([(f"Тихие часы: {q_state}", "notify:quiet_enabled")])
    rows.append([("◀️ Меню", "menu")])
    rows.append([("🩸 В пульс", "pulse")])
    return Reply(text="\n".join(lines), keyboard=rows)


def notify_action(store, p, arg=""):
    """Переключить канал/тихие часы из панели вестей."""
    key = (arg or "").strip()
    if key == "quiet_enabled":
        prefs = notify.of(p)
        new = not prefs.get("quiet_enabled", False)
        notify.set_pref(p, "quiet_enabled", new)
        store.save_player(p)
    elif key in dict(notify.CHANNELS):
        _ok, prefs = notify.toggle(notify.of(p), key)
        p.prefs = prefs
        store.save_player(p)
    return notify_screen(p)
