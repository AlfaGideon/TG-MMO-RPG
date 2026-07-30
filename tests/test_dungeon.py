"""Подземелья браузерного стека: портал наконец ведёт внутрь.

python3 tests/test_dungeon.py
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import adminmenu, adminops, combat, data, dungeon, mapview
from engine.game import Game
from engine.storage import Store
from webapp.backend import MemoryStorage

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


def fresh():
    store = Store(MemoryStorage())
    store.settings["cataclysm_notify"] = False
    store.settings["cataclysm_auto"] = False
    return store


def hero(store, game, tg_id=1, name="Герой", level=10):
    p = store.player(tg_id, name)
    game.handle(p, f"make:warrior")
    p.level = level
    p.max_hp = p.hp = 9999
    p.strength = 900
    return p


def open_portal(store, tpl_id=0):
    adminops.portal_open(store, None, tpl_id, adminmenu.pick_cell)
    tpl = dungeon.template(store, tpl_id)
    loc, x, y = map(int, tpl["portal_cell"].split(":"))
    return tpl, loc, x, y


def stand_on_portal(store, game, p, tpl_id=0):
    tpl, loc, x, y = open_portal(store, tpl_id)
    p.loc, p.x, p.y = loc, x, y
    mapview.mark_visited(p)
    return tpl, (loc, x, y)


def test_portal_leads_inside():
    print("\n— Портал ведёт внутрь, а не украшает карту —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    tpl, spot = stand_on_portal(store, game, p)

    r = game.handle(p, "look")
    check("Портал" in r.text, "портал виден при осмотре клетки")
    check(any("denter" in b[1] for row in r.keyboard for b in row),
          "есть кнопка входа")

    r = game.handle(p, "denter")
    check(dungeon.inside(p), "игрок внутри подземелья")
    check("этаж 1" in r.text, "показан первый этаж")
    check(any("dgo" in b[1] for row in r.keyboard for b in row),
          "есть кнопки перемещения")
    check(dungeon.run_of(p)["back"] == list(spot), "запомнено, куда возвращать")


def test_entry_limits():
    print("\n— Кого не пускают —")
    store = fresh()
    game = Game(store)
    p = hero(store, game, level=1)
    tpl, spot = stand_on_portal(store, game, p)

    r = game.handle(p, "denter")
    check(bool(r.alert) and "уровень" in r.alert, "низкий уровень не пускают")
    check(not dungeon.inside(p), "внутрь не попал")

    p.level = 10
    p.loc = (spot[0] + 1) % len(data.LOCATIONS)
    check(bool(game.handle(p, "denter").alert), "без портала под ногами нельзя")


def test_grid_is_derived_not_stored():
    print("\n— Сетка выводится из сида, а не хранится —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    stand_on_portal(store, game, p)
    game.handle(p, "denter")

    first = [(c["wall"], c["mob"], c["chest"])
             for c in (dungeon.cell(store, p, x, y)
                       for x in range(5) for y in range(5))]
    second = [(c["wall"], c["mob"], c["chest"])
              for c in (dungeon.cell(store, p, x, y)
                        for x in range(5) for y in range(5))]
    check(first == second, "одна и та же клетка описывается одинаково")

    run = dungeon.run_of(p)
    check("cells" not in run, "клетки не лежат в сохранении")
    blob = json.dumps(run)
    check(len(blob) < 2000, f"забег занимает мало места: {len(blob)} симв.")

    start = dungeon.cell(store, p, *dungeon.EXIT)
    check(not start["wall"], "клетка входа всегда проходима")
    check(start["exit"], "и помечена как выход")


def test_movement_and_map():
    print("\n— Перемещение и карта —")
    random.seed(5)
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    stand_on_portal(store, game, p)
    game.handle(p, "denter")

    moved = 0
    for _ in range(30):
        for d in ("s", "e", "n", "w"):
            r = game.handle(p, f"dgo:{d}")
            if not (r.alert or "").startswith("Там глухая"):
                moved += 1
                break
        while p.combat:                        # по дороге могут напасть
            combat.action(p, "hit", store.world, store)
    check(moved > 5, f"игрок ходит по подземелью: {moved} шагов")

    run = dungeon.run_of(p)
    check(len(run.get("seen") or []) > 3, "пройденное запоминается")

    m = game.handle(p, "dmap")
    check("Этаж" in m.text and "🔴" in m.text, "карта этажа рисуется")
    check("⬜" in m.text, "непройденное скрыто туманом")

    size = dungeon.size_of(dungeon.template(store, run["tpl"]))
    run["x"], run["y"] = 0, 0
    check(bool(game.handle(p, "dgo:n").alert), "за границу не выйти")


def test_content_and_progress():
    print("\n— Твари и сундуки —")
    random.seed(11)
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    stand_on_portal(store, game, p)
    game.handle(p, "denter")
    run = dungeon.run_of(p)
    size = dungeon.size_of(dungeon.template(store, run["tpl"]))

    mob_cell = chest_cell = None
    for x in range(size):
        for y in range(size):
            c = dungeon.cell(store, p, x, y)
            if c and c["mob"] and mob_cell is None:
                mob_cell = c
            if c and c["chest"] and chest_cell is None:
                chest_cell = c
    check(mob_cell is not None, "в подземелье есть твари")
    check(chest_cell is not None, "и сундуки")

    if chest_cell:
        run["x"], run["y"] = chest_cell["x"], chest_cell["y"]
        gold = p.gold
        r = game.handle(p, "dchest")
        check(p.gold > gold, f"сундук даёт золото: +{p.gold - gold}")
        check(chest_cell["key"] in run["looted"], "сундук помечен вскрытым")
        after = dungeon.cell(store, p, chest_cell["x"], chest_cell["y"])
        check(not after["chest"], "повторно не появляется")
        check(bool(game.handle(p, "dchest").alert), "второй раз не открыть")

    if mob_cell:
        run["x"], run["y"] = mob_cell["x"], mob_cell["y"]
        game.handle(p, "dfight")
        check(bool(p.combat), "бой начался")
        while p.combat:
            combat.action(p, "hit", store.world, store)
        after = dungeon.cell(store, p, mob_cell["x"], mob_cell["y"])
        check(not after["mob"], "зачищенная клетка остаётся пустой")


def test_exit_and_death():
    print("\n— Выход и гибель внутри —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    tpl, spot = stand_on_portal(store, game, p)
    game.handle(p, "denter")

    run = dungeon.run_of(p)
    run["x"], run["y"] = dungeon.EXIT
    game.handle(p, "dexit")
    check(not dungeon.inside(p), "вышел наружу")
    check((p.loc, p.x, p.y) == spot, "вернулся к порталу")

    game.handle(p, "denter")
    check(dungeon.inside(p), "зашёл снова")
    p.hp, p.max_hp, p.strength = 1, 100, 1
    boss = max(range(len(data.MOBS)), key=lambda i: data.MOBS[i][4])
    combat.start(p, boss, store=store)
    for _ in range(10):
        if not p.combat:
            break
        r = combat.action(p, "hit", store.world, store)
    check(not dungeon.inside(p), "гибель выбрасывает наружу")
    check("одземель" in r.text, "игроку это объяснили")


def test_world_button_inside():
    print("\n— «В мир» внутри ведёт в подземелье —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    stand_on_portal(store, game, p)
    game.handle(p, "denter")
    r = game.handle(p, "world")
    check("этаж" in r.text.lower(), "кнопка «В мир» показывает подземелье")

    run = dungeon.run_of(p)
    run["x"], run["y"] = dungeon.EXIT
    game.handle(p, "dexit")
    r = game.handle(p, "world")
    check("этаж" not in r.text.lower(), "снаружи — обычный мир")


def test_descend():
    print("\n— Спуск глубже —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    stand_on_portal(store, game, p)
    game.handle(p, "denter")
    run = dungeon.run_of(p)
    size = dungeon.size_of(dungeon.template(store, run["tpl"]))

    stairs = None
    for x in range(size):
        for y in range(size):
            c = dungeon.cell(store, p, x, y)
            if c and c["stairs"]:
                stairs = c
                break
        if stairs:
            break
    if stairs is None:
        check(True, "на этом этаже спуска нет — пропускаем")
        return
    run["x"], run["y"] = stairs["x"], stairs["y"]
    game.handle(p, "ddown")
    check(dungeon.run_of(p)["floor"] == 2, "спустился на второй этаж")
    check(dungeon.run_of(p)["seen"] == [], "карта нового этажа чистая")


def test_old_saves_and_panel():
    print("\n— Старые сохранения и панель —")
    backend = MemoryStorage()
    store = Store(backend)
    game = Game(store)
    p = hero(store, game)
    store.save()

    raw = json.loads(backend.get("shadowlands"))
    for pl in raw["players"].values():
        pl.pop("dungeon", None)
    backend.set("shadowlands", json.dumps(raw, ensure_ascii=False))

    again = Store(backend)
    q = again.players[p.tg_id]
    check(not dungeon.inside(q), "без поля игрок просто снаружи")
    game2 = Game(again)
    for cmd in ("world", "menu", "look"):
        try:
            game2.handle(q, cmd)
            check(True, f"экран «{cmd}» открывается")
        except Exception as e:
            check(False, f"экран «{cmd}» → {type(e).__name__}: {e}")

    from webapp.pages import world as page_world

    store2 = fresh()
    game3 = Game(store2)
    hero3 = hero(store2, game3, 7, "Ныряльщик")
    stand_on_portal(store2, game3, hero3)
    game3.handle(hero3, "denter")

    class Ctx:
        pass

    ctx = Ctx()
    ctx.store = store2
    ctx.state = {"loc": 0, "world_tab": "dungeons", "cell_pick": ""}
    try:
        markup = page_world.render(ctx)
        check("Сейчас в подземельях" in markup, "панель показывает забеги")
        check("Ныряльщик" in markup, "видно, кто внутри")
    except Exception as e:
        check(False, f"вкладка «Подземелья» → {type(e).__name__}: {e}")


def main():
    for fn in (test_portal_leads_inside, test_entry_limits,
               test_grid_is_derived_not_stored, test_movement_and_map,
               test_content_and_progress, test_exit_and_death,
               test_world_button_inside, test_descend,
               test_old_saves_and_panel):
        fn()
    print("\n" + "=" * 46)
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}:")
        for f in FAILED:
            print("   -", f)
        return 1
    print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
