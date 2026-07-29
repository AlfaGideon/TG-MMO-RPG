"""Живой мир: респавн, видимость игроков, задания.

python3 tests/test_living_world.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import combat, data, mapview, quests, respawn
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


def hero(store, game, tg_id=1, name="Герой", cls="warrior"):
    p = store.player(tg_id, name)
    game.handle(p, f"make:{cls}")
    p.max_hp = p.hp = 99999
    p.strength = 900
    return p


def mobs(store):
    return sum(1 for c in store.world.values() if c.mob >= 0)


def chests(store):
    return sum(1 for c in store.world.values() if c.chest)


def kill_on(store, game, p, cell):
    p.loc, p.x, p.y = cell.loc, cell.x, cell.y
    combat.start(p, cell.mob, store=store)
    for _ in range(40):
        if not p.combat:
            break
        combat.action(p, "hit", store.world, store)


# ── 1. Респавн ──────────────────────────────────────────────

def test_respawn_mobs():
    print("\n— Респавн: твари возвращаются —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)

    cell = next(c for c in store.world.values() if c.loc == 1 and c.mob >= 0)
    kill_on(store, game, p, cell)
    check(cell.mob < 0, "тварь убита")
    check(cell.mob_at > time.time(), "назначено время возвращения")

    p.loc, p.x, p.y = 0, 5, 5              # уходим с клетки
    cell.mob_at = time.time() - 1
    born, _ = respawn.tick(store)
    check(born == 1 and cell.mob >= 0, f"тварь вернулась (вернулось {born})")
    check(cell.mob_at == 0, "метка снята после возвращения")


def test_respawn_not_under_player():
    print("\n— Респавн не трогает клетку под игроком —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    cell = next(c for c in store.world.values() if c.loc == 1 and c.mob >= 0)
    kill_on(store, game, p, cell)
    cell.mob_at = time.time() - 1

    born, _ = respawn.tick(store)           # игрок стоит здесь же
    check(born == 0 and cell.mob < 0, "под ногами тварь не возникла")
    check(cell.mob_at > 0, "попытка отложена, а не потеряна")

    p.x = cell.x + 1 if cell.x + 1 < 9 else cell.x - 1
    cell.mob_at = time.time() - 1
    born, _ = respawn.tick(store)
    check(born == 1, "после ухода игрока тварь вернулась")


def test_respawn_chests_and_safe():
    print("\n— Респавн сундуков и покой безопасных земель —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    from engine import explore

    before = chests(store)
    cell = next(c for c in store.world.values() if c.loc == 1 and c.chest)
    p.loc, p.x, p.y = 1, cell.x, cell.y
    explore.chest(p, cell, store)
    check(chests(store) == before - 1, "сундук вскрыт")
    check(cell.chest_at > 0, "назначено появление нового")

    cell.chest_at = time.time() - 1
    _, born = respawn.tick(store)
    check(born == 1 and chests(store) == before, "сундук вернулся в локацию")

    # В безопасной локации ничего не возрождается: там и не воюют.
    safe = next(c for c in store.world.values() if c.loc == 0 and c.passable)
    safe.mob = 3
    respawn.schedule_mob(store, safe)
    check(safe.mob_at == 0, "в safe-локации метка не ставится")


def test_respawn_persists_and_switch():
    print("\n— Респавн: сохранение и выключатель —")
    store = fresh()
    cell = next(c for c in store.world.values() if c.loc == 1 and c.mob >= 0)
    respawn.schedule_mob(store, cell)
    store.save()
    again = Store(store.backend)
    check(again.world[cell.key].mob_at > 0, "метка пережила перезагрузку")

    store.settings[respawn.SETTING_ON] = False
    cell.mob_at = time.time() - 1
    check(respawn.tick(store) == (0, 0), "выключенный респавн ничего не делает")
    store.settings[respawn.SETTING_ON] = True

    respawn.set_delays(store, "mob", {"dangerous": 99})
    check(respawn._minutes(store, "mob", 1) == 99, "задержка настраивается из панели")


def test_world_not_exhaustible():
    print("\n— Мир больше не исчерпаем —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    for c in store.world.values():          # тотальная зачистка
        if c.mob >= 0:
            respawn.schedule_mob(store, c)
    check(mobs(store) == 0, "мир зачищен подчистую")

    p.loc, p.x, p.y = 0, 5, 5
    for c in store.world.values():
        if c.mob_at:
            c.mob_at = time.time() - 1
    born, _ = respawn.tick(store)
    check(born > 0 and mobs(store) > 0, f"мир населился заново: {mobs(store)} тварей")


# ── 4. Видимость игроков ────────────────────────────────────

def test_players_see_each_other():
    print("\n— Игроки видят друг друга —")
    store = fresh()
    game = Game(store)
    a = hero(store, game, 1, "Гидеон")
    b = hero(store, game, 2, "Мара", "mage")
    a.loc, a.x, a.y = 1, 5, 5
    b.loc, b.x, b.y = 1, 5, 5
    mapview.mark_visited(a)

    r = game.handle(a, "world")
    check("Мара" in r.text, "сосед по клетке виден в описании")
    check("Гидеон" not in r.text.split("Здесь же")[-1], "себя в списке нет")

    r = game.handle(a, "look")
    check("Мара" in r.text, "осмотр показывает героя")

    r = game.handle(a, "map")
    check(mapview.OTHER in r.text, "на карте синяя точка")
    check("рядом героев" in r.text, "счётчик соседей в шапке карты")

    b.loc = 2                                # ушёл в другую локацию
    r = game.handle(a, "world")
    check("Мара" not in r.text, "из другой локации не виден")


def test_others_respect_fog():
    print("\n— Соседи не светятся сквозь туман —")
    store = fresh()
    game = Game(store)
    a = hero(store, game, 1, "Гидеон")
    b = hero(store, game, 2, "Мара", "mage")
    a.loc, a.x, a.y = 1, 1, 1
    b.loc, b.x, b.y = 1, 8, 8               # далеко, в неизученном
    a.visited = []
    mapview.mark_visited(a)

    rows = mapview.grid(a, store.world, {}, mapview.other_keys(store, a))
    check(rows[8][8] == mapview.FOG, "в тумане соседа не видно")

    mapview.mark_visited(a, 1, 8, 8)        # разведали
    rows = mapview.grid(a, store.world, {}, mapview.other_keys(store, a))
    check(rows[8][8] == mapview.OTHER, "в изученной клетке виден")


# ── 2. Задания ──────────────────────────────────────────────

def test_quest_hunt():
    print("\n— Задание: охота —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)

    check("Заданий нет" in game.handle(p, "quests").text, "дневник пуст в начале")
    r = game.handle(p, "qtake:0")
    check("принято" in r.text, "задание принято")
    check(bool(game.handle(p, "qtake:0").alert), "дважды одно не взять")

    q = next(q for q in data.QUESTS if q[0] == 0)
    need = quests.fields(q)["need"]
    killed = 0
    while killed < need:
        cell = next((c for c in store.world.values()
                     if c.mob == 0 and c.passable), None)
        if cell is None:                    # кончились — ждём респавна
            p.loc, p.x, p.y = 0, 5, 5
            for c in store.world.values():
                if c.mob_at:
                    c.mob_at = time.time() - 1
            respawn.tick(store)
            continue
        kill_on(store, game, p, cell)
        killed += 1
    check(quests.complete(p, q), f"после {need} убийств задание готово")

    gold = p.gold
    r = game.handle(p, "qdone:0")
    check("выполнено" in r.text and p.gold > gold, "сдано, награда получена")
    check(bool(game.handle(p, "qdone:0").alert), "повторно не сдать")


def test_quest_deliver_and_reach():
    print("\n— Задание: доставка и разведка —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)

    game.handle(p, "qtake:5")               # принести зелье здоровья (idx 8)
    check(bool(game.handle(p, "qdone:5").alert), "без предмета не сдать")
    p.inventory.append(8)
    r = game.handle(p, "qdone:5")
    check("выполнено" in r.text, "с предметом сдано")
    check(8 not in p.inventory, "предмет ушёл заказчику")

    p.level = 5
    game.handle(p, "qtake:4")               # дойти до Катакомб (loc 3)
    q = next(q for q in data.QUESTS if q[0] == 4)
    check(not quests.complete(p, q), "пока не дошёл — не выполнено")
    quests.on_enter(p, 3)
    check(quests.complete(p, q), "приход в локацию засчитан")


def test_quest_daily_and_npc():
    print("\n— Ежедневные и выдача у NPC —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)

    rows = quests.offer_rows(p, 0)
    check(rows, f"Старейшина предлагает задания: {len(rows)}")
    t = game.handle(p, "talk:0")
    check(any("qtake" in b[1] for row in t.keyboard for b in row),
          "кнопки заданий есть в диалоге")

    game.handle(p, "qtake:7")               # ежедневное
    p.quests["7"] = {"n": 3, "done": False}
    game.handle(p, "qdone:7")
    check("7" not in p.quests, "ежедневное снялось — завтра можно снова")

    p.quest_day = "2020-01-01"
    p.quests["7"] = {"n": 1, "done": False}
    check(quests.refresh_daily(p), "суточный сброс сработал")
    check("7" not in p.quests, "прогресс ежедневного обнулён")

    p.level = 1
    high = [q for q in data.QUESTS if quests.fields(q)["level"] > 1]
    if high:
        qid = quests.fields(high[0])["id"]
        check(bool(game.handle(p, f"qtake:{qid}").alert),
              "задание не по уровню не взять")


def test_quest_survives_reload():
    print("\n— Задания переживают перезагрузку —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    game.handle(p, "qtake:0")
    p.quests["0"]["n"] = 2
    store.save_player(p)

    again = Store(store.backend)
    q = again.players[p.tg_id]
    check(q.quests.get("0", {}).get("n") == 2, "прогресс сохранён")
    check(quests.active(q), "задание осталось активным")


def main():
    for fn in (test_respawn_mobs, test_respawn_not_under_player,
               test_respawn_chests_and_safe, test_respawn_persists_and_switch,
               test_world_not_exhaustible,
               test_players_see_each_other, test_others_respect_fog,
               test_quest_hunt, test_quest_deliver_and_reach,
               test_quest_daily_and_npc, test_quest_survives_reload):
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
