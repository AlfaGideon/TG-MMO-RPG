"""🔕 Настройки вестей: дефолты, тумблеры, экран и тихие часы.

python3 tests/test_engine_notify.py
"""
import os
import random
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import notify, progress
from engine.game import Game
from engine.models import Player
from engine.storage import Store
from webapp.backend import MemoryStorage

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


def main():
    random.seed(5)
    store = Store(MemoryStorage())
    game = Game(store)
    p = Player(tg_id=1, cls="mage", level=2)
    store.save_player(p)

    print("\n— Дефолты и нормализация —")
    d = notify.normalized(None)
    check(all(d[k] for k in ("auction", "portal", "duel")), "каналы включены")
    check(d["quiet_enabled"] is False, "тихие часы выключены по умолчанию")
    check(notify.enabled({}, "auction") is True, "без настроек канал доступен")
    check(notify.enabled({}, "нет_такого") is False, "незнакомый канал закрыт")
    bad = notify.normalized({"auction": "yes", "quiet_start": "25:99"})
    check(bad["auction"] is True, "битое значение канала откатывается в дефолт")
    check(bad["quiet_start"] == "22:00", "битое время остаётся дефолтным")

    print("\n— Тумблер —")
    _ok, prefs = notify.toggle(notify.normalized({}), "auction")
    check(_ok is False and prefs["auction"] is False, "аукцион выключен")
    _ok2, prefs2 = notify.toggle(prefs, "auction")
    check(_ok2 is True and prefs2["auction"] is True, "возврат включён")

    print("\n— Тихие часы (фиксированное время) —")
    prefs_q = notify.normalized({
        "quiet_enabled": True, "quiet_start": "22:00", "quiet_end": "08:00"})
    night = datetime(2026, 9, 6, 23, 30).timestamp()
    day = datetime(2026, 9, 6, 12, 30).timestamp()
    check(notify.in_quiet_hours(prefs_q, night) is True, "ночь — тихие часы")
    check(notify.in_quiet_hours(prefs_q, day) is False, "день — вести можно")

    print("\n— Экран и маршрут —")
    screen = progress.notify_screen(p)
    check("Центр вестей" in screen.text, "экран открывается")
    check("⏳ Аукцион: <b>✅ вкл</b>" in screen.text, "канал виден")
    routed = game.handle(p, "notify")
    check("Центр вестей" in routed.text, "`notify` доходит до экрана")
    toggled = game.handle(p, "notify:auction")
    check("⏳ Аукцион: <b>⛔ выкл</b>" in toggled.text, "тумблер из меню работает")
    check(notify.enabled(p.prefs, "auction") is False, "настройка сохранена у героя")
    q3 = game.handle(p, "notify:quiet_enabled")
    check("🌙 вкл" in q3.text, "тихие часы включились из экрана")

    print("\n" + "=" * 46)
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}")
        for f in FAILED:
            print("   -", f)
        return 1
    print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
