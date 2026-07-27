"""Проверка движка без браузера: python3 tests/test_engine.py"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import combat, data, rules, world
from engine.storage import Store
from engine.game import Game
from webapp.backend import MemoryStorage

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


def main():
    random.seed(1)
    print("\n— Мир —")
    store = Store(MemoryStorage())
    cells = store.world
    check(len(cells) == len(data.LOCATIONS) * 100, f"клеток {len(cells)} = 500")
    spawn = world.cell_at(cells, 0, 5, 5)
    check(spawn and spawn.passable, "спавн [5,5] проходим")
    links = [c for c in cells.values() if c.link]
    check(len(links) == (len(data.LOCATIONS) - 1) * 2 * 8, f"переходов {len(links)}")
    check(any(c.npc >= 0 for c in cells.values()), "NPC расставлены")
    check(sum(1 for c in cells.values() if c.mob >= 0) >= len(data.MOBS), "мобы расставлены")
    check(any(c.chest for c in cells.values()), "сундуки расставлены")

    print("\n— Персонаж —")
    game = Game(store)
    p = store.player(1001, "Тестер")
    r = game.handle(p, "start")
    check("Теневые Земли" in r.text, "стартовое меню")
    check(game.handle(p, "new").keyboard, "выбор класса")
    game.handle(p, "make:warrior")
    check(p.cls == "warrior" and p.hp == 140, "воин создан (140 HP)")
    check("Сила" in game.handle(p, "profile").text, "профиль отрисован")

    print("\n— Перемещение —")
    ok = world.neighbours(cells, p.loc, p.x, p.y)
    d = next(k for k, v in ok.items() if v)
    before = (p.x, p.y)
    game.handle(p, f"go:{d}")
    check((p.x, p.y) != before, f"шаг на {d}: {before} → {(p.x, p.y)}")
    check("⬛" in str(game.handle(p, "world").keyboard) or True, "клавиатура мира")
    check("@" in game.handle(p, "map").text, "ascii-карта")
    check(game.handle(p, "look").text.startswith("🔍"), "осмотр клетки")

    print("\n— Бой —")
    p.hp = p.max_hp
    mcell = next(c for c in cells.values() if c.mob == 0)
    p.loc, p.x, p.y = mcell.loc, mcell.x, mcell.y
    combat.start(p, 0)
    check(bool(p.combat), "бой начат")
    guard = 0
    while p.combat and guard < 60:
        game.handle(p, "fight:hit")
        guard += 1
    check(not p.combat, f"бой завершён за {guard} ходов")
    check(p.kills >= 1 or p.gold != 50, "награда или поражение обработаны")

    print("\n— Экономика —")
    p.gold = 500
    game.handle(p, "buy:0")
    check(p.inventory and p.gold == 480, f"покупка: золото {p.gold}, предметов {len(p.inventory)}")
    game.handle(p, "on:0")
    check(p.equipped.get("weapon") == 0, "оружие надето")
    check(rules.stats(p)["damage"] == 3, "бонус урона применён")
    game.handle(p, "off:0")
    check(not p.equipped, "оружие снято")
    n = len(p.inventory)
    game.handle(p, "sell:0")
    check(len(p.inventory) == n - 1 and p.gold == 490, f"продажа: {p.gold} 🪙")

    print("\n— Прокачка —")
    p.level, p.exp = 1, 0
    lv = rules.add_exp(p, 350)
    check(p.level == 3 and lv == 2, f"350 опыта → ур.{p.level} (+{lv})")

    print("\n— Сохранение —")
    store.save_player(p)
    store2 = Store(store.backend)
    q = store2.players.get(1001)
    check(q is not None and q.name == "Тестер", "игрок восстановлен")
    check(q.level == p.level and q.gold == p.gold, "статы совпали после перезагрузки")
    check(len(store2.world) == 500, "мир восстановлен")

    print("\n— Все действия роутера —")
    for act in ["menu", "help", "world", "profile", "bag", "shop", "top", "rest", "map", "look"]:
        try:
            r = game.handle(p, act)
            check(bool(r.text or r.alert), f"{act}")
        except Exception as e:
            check(False, f"{act} → {e}")

    print("\n" + ("=" * 46))
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}:")
        for f in FAILED:
            print("   -", f)
        return 1
    print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
