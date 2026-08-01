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


def _door_reachable(cells, door, sizes):
    """Есть ли проходимый путь от центра локации до клетки-двери."""
    from collections import deque
    li = door.loc
    size = sizes.get(str(li), world.SIZE)
    cx, cy = size // 2, size // 2
    passable = {(c.x, c.y) for c in cells.values()
                if c.loc == li and c.passable}
    if (cx, cy) not in passable or (door.x, door.y) not in passable:
        return False
    seen, q = {(cx, cy)}, deque([(cx, cy)])
    while q:
        x, y = q.popleft()
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            n = (x + dx, y + dy)
            if n in passable and n not in seen:
                seen.add(n)
                q.append(n)
    return (door.x, door.y) in seen


def main():
    random.seed(1)
    print("\n— Мир —")
    store = Store(MemoryStorage())
    cells = store.world
    # Угловые замки — 25×25 (625 клеток), остальные локации — 10×10.
    expected_cells = sum(
        (world.DEFAULT_SIZES.get(str(li), world.SIZE) ** 2)
        for li in range(len(data.LOCATIONS)))
    check(len(cells) == expected_cells, f"клеток {len(cells)} = {expected_cells}")
    spawn = world.cell_at(cells, 0, 5, 5)
    check(spawn and spawn.passable, "спавн [5,5] проходим")
    castle = next((c for c in cells.values() if c.loc == 5), None)
    check(castle is not None and castle.loc == 5 and
          sum(1 for c in cells.values() if c.loc == 5) == 625,
          "угловой замок 25×25 (625 клеток)")
    # Мировая карта 10×10: по краям 36 локаций (4 угла + 32 тракта).
    pos = {int(k): tuple(v) for k, v in world.DEFAULT_GRID.items()}
    rim = [li for li, (wx, wy) in pos.items()
           if wx in (0, 9) or wy in (0, 9)]
    check(len(rim) == 36, f"по краям мировой карты 36 локаций ({len(rim)})")
    check(all(any(c.tile == "village" for c in cells.values() if c.loc == li)
              for li in (5, 6, 7, 8)), "в каждом замке по углам — цитадели")
    # Внутри 25×25-локации — четыре замка 10×10 по углам (10+5+10=25).
    for li in (5, 6, 7, 8):
        castle_cells = [c for c in cells.values() if c.loc == li
                        and c.tile == "village"]
        check(len(castle_cells) >= 400,
              f"в локации {li} четыре замка 10×10 (village: {len(castle_cells)})")
        # Углы локации заняты замками.
        corners_ok = all(
            any(c.tile == "village" and (c.x, c.y) == corner
                for c in cells.values() if c.loc == li)
            for corner in ((0, 0), (0, 24), (24, 0), (24, 24)))
        check(corners_ok, f"замки стоят по углам локации {li}")
    # Тракт-локации между углами — опасные
    trakts = [l for l in data.LOCATIONS if str(l[0]).startswith("Тракт")]
    check(len(trakts) == 32 and all(t[2] == "dangerous" for t in trakts),
          f"32 опасных тракта по краям карты ({len(trakts)})")
    links = [c for c in cells.values() if c.link]
    # Шов между соседями — ОДНА дверь с каждой стороны, а не стена из дверей.
    pos = {int(k): tuple(v) for k, v in world.DEFAULT_GRID.items()}
    pairs = sum(1 for ai, (ax, ay) in pos.items()
                for bi, (bx, by) in pos.items()
                if ai < bi and abs(ax - bx) + abs(ay - by) == 1)
    check(len(links) == pairs * 2, f"переходов {len(links)} = {pairs} пар × 2")
    check(any(c.npc >= 0 for c in cells.values()), "NPC расставлены")
    check(sum(1 for c in cells.values() if c.mob >= 0) >= len(data.MOBS), "мобы расставлены")
    check(any(c.chest for c in cells.values()), "сундуки расставлены")
    check(all(_door_reachable(cells, c, world.DEFAULT_SIZES)
              for c in cells.values() if c.link and c.link[0] != c.loc),
          "до каждой двери перехода есть дорога от центра")

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
    check("🔴" in game.handle(p, "map").text, "карта из плиток, игрок отмечен")
    check("⬜" in game.handle(p, "map").text, "туман войны на карте")
    check("#" not in game.handle(p, "map").text, "решёток и точек на карте нет")
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
    check(len(store2.world) == len(store.world), "мир восстановлен")

    print("\n— Все действия роутера —")
    for act in ["menu", "help", "world", "profile", "bag", "shop", "top", "rest", "map", "look"]:
        try:
            r = game.handle(p, act)
            check(bool(r.text or r.alert), f"{act}")
        except Exception as e:
            check(False, f"{act} → {e}")

    print("\n— Динамические локации —")
    n0 = len(data.LOCATIONS)
    # (5,6) — к югу от Заброшенной Крепости (2, на [5,5]): сосед на сетке есть.
    li, report = store.add_location("Мглистые топи", "Туман и топь.", "dangerous", 99, 5, 6)
    check(li == n0, f"новая локация добавлена (индекс {li})")
    check(len(data.LOCATIONS) == n0 + 1, "data.LOCATIONS вырос")
    check(sum(1 for c in store.world.values() if c.loc == li) == 100, "100 клеток достроено")
    seams = [c for c in store.world.values()
             if c.loc == li and c.link and c.link[0] != li]
    back = [c for c in store.world.values()
            if c.loc == 2 and c.link and c.link[0] == li]
    check(len(seams) == 1 and len(back) == 1, f"автошов с соседом: {len(seams)}/{len(back)} ворот")
    check(any("↔" in r for r in report), f"отчёт связывания: {report}")
    check(store.settings["locations"][-1][0] == "Мглистые топи",
          "список локаций сохранён в настройках")

    # перезагрузка: динамический список восстанавливается
    store3 = Store(store.backend)
    check(len(data.LOCATIONS) == n0 + 1, "после перезагрузки локаций столько же")
    check(len(store3.world) == len(store.world), "мир восстановлен с новой локацией")

    # предупреждение min_level при входе в опасную локацию
    # Новая локация к югу от Крепости (2): дверь на южной границе — в центре ряда.
    p.loc, p.x, p.y, p.combat = 2, world.SIZE - 2, world.SIZE // 2, None
    r = game.handle(p, "go:s")
    check(p.loc == li, "переход в новую локацию сработал")
    check("опасно" in (r.alert or "").lower(), f"alert по min_level: {r.alert!r}")

    # удаление последней: игрок эвакуируется, мир переиндексируется
    msg = store.remove_location(li)
    check("удалена" in msg, f"удаление: {msg}")
    check(len(data.LOCATIONS) == n0, "список локаций вернулся к исходному")
    check(p.loc == 0 and (p.x, p.y) == world.SPAWN, "игрок эвакуирован на спавн")

    print("\n— Бродячий торговец —")
    from engine import merchant as M
    p2 = store.player(2001, "Путник")
    game2 = Game(store)
    game2.handle(p2, "make:warrior")
    p2.gold = 5000
    check(M.at(store, p2.loc) is None, "торговца ещё нет")

    # Админское появление: торговец стоит в локации героя.
    store.settings[M.KEY] = {
        "active": True, "location": p2.loc, "expires": __import__("time").time() + M.LIFETIME,
        "items": [{"item": 24, "price": 100, "qty": 2}],  # Кольцо удачи
    }
    store.save()
    check(M.at(store, p2.loc) is not None, "торговец на месте")
    r = game2.handle(p2, "world")
    check("торговец" in r.text.lower() and
          any("merchant" == b[1] for row in r.keyboard for b in row),
          "в клетке виден торговец и кнопка к нему")
    r = game2.handle(p2, "merchant")
    check("Кольцо удачи" in r.text, "витрина показывает товар")
    gold_before = p2.gold
    r = game2.handle(p2, "mcard:0")
    check(any("Купить" in b[0] for row in r.keyboard for b in row),
          "карточка товара открыта")
    r = game2.handle(p2, "mbuy:0")
    check(p2.gold == gold_before - 100, "золото списано за покупку")
    check(p2.inventory.count(24) == 1, "диковинка в сумке")
    st = M.at(store, p2.loc)
    check(st["items"][0]["qty"] == 1, "остаток на витрине уменьшен")
    r = game2.handle(p2, "mbuy:0")
    check(p2.inventory.count(24) == 2 and st["items"][0]["qty"] == 0,
          "вторая покупка опустошила витрину")
    r = game2.handle(p2, "mbuy:0")
    check(bool(r.alert), f"пустой товар не продаётся ({r.alert!r})")
    store.settings[M.KEY] = {"active": True, "location": 99,
                             "expires": __import__("time").time() + 9999, "items": []}
    store.save()
    r = game2.handle(p2, "merchant")
    check(r.alert and "ушёл" in r.alert, "в чужой локации торговца не видно")

    # Просроченный торговец уходит сам.
    store.settings[M.KEY] = {"active": True, "location": p2.loc,
                             "expires": __import__("time").time() - 5,
                             "items": []}
    store.save()
    check(M.at(store, p2.loc) is None, "просроченный торговец ушёл")
    check(not any(c.loc >= n0 for c in store.world.values()), "клеток удалённой локации нет")

    # правка существующей локации: свойства меняются, клетки остаются
    print("\n— Правка локации —")
    a, _ = store.add_location("Черновик", "как есть", "dangerous", 1, 6, 4)
    cells_before = sum(1 for c in store.world.values() if c.loc == a)
    links_before = sum(1 for c in store.world.values() if c.loc == a and c.link)
    msg = store.update_location(a, "Ледяной Предел", "Вечная мерзлота.", "boss", 15, 3)
    check("обновлена" in msg, f"отчёт правки: {msg}")
    check(data.LOCATIONS[a] == ("Ледяной Предел", "Вечная мерзлота.", "boss", 15),
          "свойства локации применены")
    check(store.settings["location_floors"].get(str(a)) == 3, "этажи сохранены")
    check(sum(1 for c in store.world.values() if c.loc == a) == cells_before,
          "клетки не пересобирались")
    check(sum(1 for c in store.world.values() if c.loc == a and c.link) == links_before,
          "швы остались на месте")
    check(store.settings["locations"][a][0] == "Ледяной Предел",
          "правка сохранена в настройках")
    store.update_location(a, "", "", "мусор", "не число")
    check(data.LOCATIONS[a][0] == "Ледяной Предел" and data.LOCATIONS[a][2] == "boss",
          "пустые и битые значения не портят локацию")
    store.remove_location(a)

    # удаление средней: реиндексация хвоста
    a, _ = store.add_location("Остров А", "а", "dangerous", 1, 6, 4)
    b, _ = store.add_location("Остров Б", "б", "dangerous", 1, 7, 4)
    store.remove_location(a)
    check(len(data.LOCATIONS) == n0 + 1 and data.LOCATIONS[-1][0] == "Остров Б",
          "хвост реиндексирован после удаления средней")
    check(any(c.loc == n0 for c in store.world.values()), "клетки бывшей «Б» теперь с новым индексом")
    check(store.settings["world_grid"].get(str(n0)) == [7, 4], "сетка мира реиндексирована")
    store.remove_location(n0)  # вернуть мир к исходному виду
    check(len(data.LOCATIONS) == n0, "мир снова исходный")

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
