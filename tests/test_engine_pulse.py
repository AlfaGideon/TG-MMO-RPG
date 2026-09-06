"""🩸 Пульс героя: браузерный экран собирает живые данные без нового состояния.

python3 tests/test_engine_pulse.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import cataclysm, pulse, quests, siege, worldboss
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
    p = Player(tg_id=1, cls="berserker", level=3)

    print("\n— Экран без событий —")
    r = pulse.pulse(p, store)
    check(r.text.startswith("🩸 <b>Пульс героя</b>"), "шапка есть")
    check("📜 <b>Задания</b>" not in r.text, "без заданий секция не рисуется")
    check("🌍 <b>Мир</b>" in r.text, "фаза луны всегда в «Мире»")
    check(any(k == "pulse" for row in game.menu(p).keyboard for _, k in row),
          "кнопка «Пульс» есть в меню движка")

    print("\n— Активные задания, катаклизм, босс, осада —")
    store.save_player(p)
    quests.take(p, 0)
    cataclysm.strike(store, "plague")
    worldboss.summon(store, "leviathan", loc=1)
    siege.start(store, "cult", 0)
    r2 = pulse.pulse(p, store)
    check("📜 <b>Задания</b>" in r2.text, "секция заданий появилась")
    check("Проредить болото" in r2.text, "первое задание подписано")
    check("Мор" in r2.text, "катаклизм в пульсе")
    check("Левиафан Бездны" in r2.text, "мировой босс в пульсе")
    check("Погост Костров" in r2.text, "осада в пульсе")
    check(any(label.startswith("🏰") for label, _ in r2.keyboard[0]),
          "кнопка перехода к боссу появилась")

    print("\n— Маршрут из меню движка —")
    routed = game.handle(p, "pulse")
    check(routed.text.startswith("🩸"), "`pulse` доходит до экрана")

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
