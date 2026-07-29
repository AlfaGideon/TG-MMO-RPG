"""Катаклизмы и сиды мира: python3 tests/test_cataclysm.py"""
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import cataclysm as C
from engine import adminops, combat, data, world
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
    store.settings["cataclysm_auto"] = False   # авто-беды не мешают тестам
    store.settings["cataclysm_notify"] = False
    return store


def test_seeds():
    print("\n— Сиды мира —")
    store = fresh()
    seeds = store.seeds()
    check(set(seeds) == set(world.SEED_KEYS), f"{len(seeds)} сидов: {list(seeds)}")
    check(len(set(seeds.values())) == len(seeds), "все сиды различны")
    check(store.seeds() == seeds, "сиды детерминированы")

    store.settings["seed"] = 4242
    check(store.seeds() != seeds, "смена базового сида двигает все частные")

    store.set_seeds({"chests": 777})
    check(store.seeds()["chests"] == 777, "частный сид сохранён")
    check(store.seeds()["terrain"] != 777, "остальные сиды не тронуты")
    store.set_seeds({"chests": 0})
    check(store.seeds()["chests"] != 777, "0 возвращает вывод из базового")

    # Разный сид сундуков — другая добыча при том же рельефе.
    a = world.generate(1337, seeds={**store.seeds(), "chests": 1})
    b = world.generate(1337, seeds={**store.seeds(), "chests": 2})
    walls_a = {k for k, c in a.items() if not c.passable}
    walls_b = {k for k, c in b.items() if not c.passable}
    chests_a = {k for k, c in a.items() if c.chest}
    chests_b = {k for k, c in b.items() if c.chest}
    check(walls_a == walls_b, "рельеф не зависит от сида сундуков")
    check(chests_a != chests_b, "сид сундуков меняет их расстановку")


def test_strike_and_revert():
    print("\n— Удар и откат —")
    store = fresh()
    before = {k: (c.tile, c.passable, c.mob, c.chest) for k, c in store.world.items()}

    ev = C.strike(store, "wildfire", loc=1)
    check(ev["cells"] > 0, f"пожар накрыл {ev['cells']} клеток")
    after = {k: (c.tile, c.passable, c.mob, c.chest) for k, c in store.world.items()}
    changed = [k for k in before if before[k] != after[k]]
    check(changed, f"клетки изменились: {len(changed)}")
    check(all(k.startswith("1:") for k in changed), "затронута только локация 1")

    live = C.active(store, 1)
    check(len(live) == 1, "бедствие числится живым в локации 1")
    check(not C.active(store, 0), "соседняя локация не тронута")

    C.end(store, ev["id"])
    back = {k: (c.tile, c.passable, c.mob, c.chest) for k, c in store.world.items()}
    check(back == before, "откат вернул клетки как было")
    check(not C.active(store, 1), "бедствие снято")


def test_protection():
    print("\n— Что беда не трогает —")
    store = fresh()
    p = store.player(1, "Хранитель")
    p.cls, p.loc, p.x, p.y = "warrior", 2, 3, 3
    store.save_player(p)
    seams = [c.key for c in store.world.values() if c.link]

    ev = C.strike(store, "quake", loc=C.GLOBAL)
    snap = ev["snapshot"]
    check(f"2:3:3" not in snap, "клетка под игроком не тронута")
    check(not any(k in snap for k in seams), "швы-переходы не тронуты")
    check(f"0:{world.SPAWN[0]}:{world.SPAWN[1]}" not in snap, "спавн не тронут")
    C.end(store, ev["id"])


def test_effects():
    print("\n— Множители правил —")
    store = fresh()
    check(C.effects(store, 0)["mob_rate"] == 1.0, "в покое множители нейтральны")

    C.strike(store, "bloodmoon", loc=C.GLOBAL)
    eff = C.effects(store, 0)
    check(eff["mob_rate"] > 1.5, f"кровавая луна злее: ×{eff['mob_rate']:.2f}")
    check(eff["loot"] > 1.0, "добыча щедрее")
    check("Кровавая луна" in C.banner(store, 0), "баннер показывает бедствие")

    C.strike(store, "plague", loc=0)
    stacked = C.effects(store, 0)
    check(stacked["mob_rate"] > eff["mob_rate"], "два бедствия перемножаются")
    check(C.effects(store, 1)["mob_rate"] == eff["mob_rate"], "мор виден только в своей локации")


def test_expiry():
    print("\n— Срок и авто-снятие —")
    store = fresh()
    ev = C.strike(store, "flood", loc=0, hours=1)
    ev["until"] = time.time() - 1        # искусственно просрочим
    check(C.tick(store) == 1, "истёкшее бедствие снято тиком")
    check(not C.active(store, 0), "живых бедствий не осталось")

    store.settings["cataclysm_auto"] = True
    store.settings["cataclysm_chance"] = 1.0
    store.settings["cataclysm_limit"] = 1
    check(C.auto(store) is not None, "авто-катаклизм сработал при шансе 1.0")
    check(C.auto(store) is None, "лимит одновременных соблюдён")


def test_admin_and_game():
    print("\n— Панель и игра —")
    store = fresh()

    class Guest:
        tg_id, name = 5, "Гость"
        web_admin_role, web_admin_caps = "viewer", []

    try:
        adminops.cataclysm_strike(store, Guest(), "meteor", 0)
        check(False, "наблюдателю запрещено насылать беды")
    except adminops.Denied:
        check(True, "наблюдателю запрещено насылать беды")

    ev, info = adminops.cataclysm_strike(store, None, "meteor", 0)
    check("Звездопад" in info, f"владелец панели ударил: {info}")
    try:
        adminops.cataclysm_strike(store, None, "meteor", 0)
        check(False, "повтор того же бедствия отклонён")
    except adminops.Denied:
        check(True, "повтор того же бедствия отклонён")

    game = Game(store)
    p = store.player(9, "Ходок")
    game.handle(p, "make:warrior")
    p.loc = 0
    r = game.handle(p, "world")
    check("⚠️" in r.text, "игрок видит предупреждение в клетке")
    check(any("disaster" in b[1] for row in r.keyboard for b in row),
          "кнопка «Что происходит?» появилась")
    card = game.handle(p, "disaster")
    check("Звездопад" in card.text, "карточка бедствия открывается")

    n = adminops.cataclysm_calm(store, None)
    check(n == 1, f"успокоено бедствий: {n}")
    check("⚠️" not in game.handle(p, "world").text, "предупреждение исчезло")


def mobs_in(store, loc=None):
    return sum(1 for c in store.world.values()
               if c.mob >= 0 and (loc is None or c.loc == loc))


def test_horde():
    print("\n— Орда: вдвое больше тварей —")
    store = fresh()
    base = mobs_in(store, 1)
    ev = C.strike(store, "bloodmoon", loc=1)
    check(mobs_in(store, 1) == base * 2, f"мобов в беде: {base} → {mobs_in(store, 1)}")
    check(mobs_in(store, 2) == mobs_in(fresh(), 2), "соседняя локация не тронута")

    # Второе бедствие там же не даёт четырёхкратной оравы.
    ev2 = C.strike(store, "plague", loc=1)
    check(mobs_in(store, 1) == base * 2, "два бедствия — всё те же ×2")
    C.end(store, ev["id"])
    check(mobs_in(store, 1) == base * 2, "пока одно живо, орда держится")
    C.end(store, ev2["id"])
    check(mobs_in(store, 1) == base, f"после конца норма: {mobs_in(store, 1)}")
    check(not store.settings.get("cataclysm_horde"), "список орды очищен")


def test_horde_keeps_kills():
    print("\n— Убитых орда не воскрешает —")
    store = fresh()
    base = mobs_in(store, 1)
    ev = C.strike(store, "wildfire", loc=1)
    horde = list(store.settings["cataclysm_horde"])
    check(horde, "орда отмечена в настройках")

    for key in horde[:3]:                     # игрок «зачистил» троих
        store.world[key].mob = -1
    C.end(store, ev["id"])
    check(mobs_in(store, 1) == base, "популяция вернулась к мирной норме")

    # Мирные твари, убитые во время беды, тоже остаются убитыми.
    store2 = fresh()
    victim = next(c for c in store2.world.values() if c.loc == 1 and c.mob >= 0)
    ev = C.strike(store2, "quake", loc=1)
    victim.mob = -1
    C.end(store2, ev["id"])
    check(victim.mob == -1, "убитая мирная тварь не воскресла")


def test_aggression():
    print("\n— Агрессия: засады и подкрепление —")
    store = fresh()
    game = Game(store)
    p = store.player(1, "Ходок")
    game.handle(p, "make:warrior")
    p.loc, p.x, p.y = 1, 5, 5
    p.max_hp = p.hp = 99999

    eff = C.effects(store, 1)
    check(eff["ambush"] == 0 and eff["join"] == 0, "в мире твари не агрессивны")
    check(all(C.prowl(store, p) is None for _ in range(200)),
          "без беды засад не бывает")

    C.strike(store, "bloodmoon", loc=1)
    eff = C.effects(store, 1)
    check(eff["ambush"] > 0.3 and eff["join"] > 0.2,
          f"в беду твари злые: засада {eff['ambush']}, подмога {eff['join']}")

    # Засада: моб уходит со своей клетки в бой, а не остаётся ждать снова.
    random.seed(3)
    hits = 0
    for _ in range(300):
        snap = {c.key: c.mob for c in store.world.values() if c.loc == 1}
        p.combat = {}
        if C.prowl(store, p) is not None:
            hits += 1
        for c in store.world.values():
            if c.loc == 1:
                c.mob = snap.get(c.key, c.mob)
    check(hits > 50, f"засады случаются: {hits}/300")

    # Внезапный удар бьёт первым.
    p.combat = {}
    p.hp = 99999
    r = combat.start(p, 0, ambush=True, store=store)
    check("из засады" in r.text, "игрок видит, что напали первым")
    check(p.hp < 99999 or "отпрянул" in r.text, "внезапный удар прошёл или уклонён")

    # Подкрепление подтягивается к идущему бою.
    weak = store.player(2, "Слабый")
    game.handle(weak, "make:mage")
    weak.loc, weak.max_hp, weak.hp, weak.strength = 1, 99999, 99999, 1
    cell = next(c for c in store.world.values()
                if c.loc == 1 and c.mob >= 0 and c.passable)
    weak.x, weak.y = cell.x, cell.y
    combat.start(weak, cell.mob, store=store)
    joined, text = 0, ""
    for _ in range(60):
        if not weak.combat:
            break
        before = len(weak.combat.get("queue") or [])
        r = combat.action(weak, "block", store.world, store)
        text = r.text or text
        if weak.combat and len(weak.combat.get("queue") or []) > before:
            joined += 1
    check(joined > 0, f"подкреплений подтянулось: {joined}")
    check("Ждут своей очереди" in text, "очередь врагов видна в бою")


def test_queue_combat():
    print("\n— Бой со сворой —")
    store = fresh()
    game = Game(store)
    p = store.player(1, "Боец")
    game.handle(p, "make:warrior")
    p.loc, p.max_hp, p.hp, p.strength = 1, 99999, 99999, 500
    cell = next(c for c in store.world.values() if c.loc == 1 and c.mob >= 0)
    p.x, p.y = cell.x, cell.y

    combat.start(p, cell.mob, store=store)
    combat.join(p, 1)
    combat.join(p, 0)
    check(len(p.combat["queue"]) == 2, "двое ждут очереди")

    gold_before = p.gold
    r = combat.action(p, "hit", store.world, store)
    check(bool(p.combat), "после первого убитого бой продолжается")
    check(p.gold > gold_before, "награда за поверженного начислена сразу")
    check(len(p.combat["queue"]) == 1, "очередь укоротилась")
    check(cell.mob >= 0, "клетка ещё занята: свора не добита")

    for _ in range(10):
        if not p.combat:
            break
        r = combat.action(p, "hit", store.world, store)
    check(not p.combat, "свора добита — бой окончен")
    check(cell.mob < 0, "клетка очищена только в конце")
    check("Победа" in r.text, "итоговый экран победы")


def test_bot_menu():
    print("\n— Админка в боте —")
    from engine import permissions

    store = fresh()
    game = Game(store)
    p = store.player(1, "Босс")
    game.handle(p, "make:warrior")
    p.is_web_admin = True
    p.web_admin_role = "admin"
    p.web_admin_caps = permissions.rank_caps("admin")

    r = game.handle(p, "adm:cata")
    hits = [b for row in r.keyboard for b in row if b[1].startswith("adm:catahit:")]
    check(len(hits) == len(C.ORDER), f"кнопок удара: {len(hits)}")

    game.handle(p, "adm:catahit:wildfire")
    live = C.active(store, None)
    check(len(live) == 1, "бедствие запущено из бота")

    r = game.handle(p, f"adm:cataoff:{live[0]['id']}")
    check(not C.active(store, None), "бедствие снято из бота")

    guest = store.player(2, "Гость")
    guest.is_web_admin = True
    guest.web_admin_role = "viewer"
    guest.web_admin_caps = permissions.rank_caps("viewer")
    check("Нет права" in game.handle(guest, "adm:cata").alert,
          "наблюдателю раздел закрыт")


def test_history():
    print("\n— Летопись —")
    store = fresh()
    ev = C.strike(store, "blizzard", loc=1)
    C.end(store, ev["id"])
    log = C.history(store)
    check(len(log) >= 2, f"записей в летописи: {len(log)}")
    check(log[0]["what"] == "утих", "последняя запись — окончание")
    check(C.place(C.GLOBAL) == "🌍 Весь мир", "глобальная беда подписана")
    check(C.place(1) == data.LOCATIONS[1][0], "локальная беда подписана именем")


def main():
    for fn in (test_seeds, test_strike_and_revert, test_protection, test_effects,
               test_expiry, test_horde, test_horde_keeps_kills,
               test_aggression, test_queue_combat, test_admin_and_game,
               test_bot_menu, test_history):
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
