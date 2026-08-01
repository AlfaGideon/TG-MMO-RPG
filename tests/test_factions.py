"""Фракции и репутация: выбор стороны, скидки, реакция мира.

python3 tests/test_factions.py
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import combat, data, death, factions as F, shop
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


def hero(store, game, tg_id=1, name="Герой"):
    p = store.player(tg_id, name)
    game.handle(p, "make:warrior")
    p.loc, p.x, p.y = 0, 5, 5
    p.max_hp = p.hp = 9999
    p.strength = 900
    return p


def test_opposing_interests():
    print("\n— Помощь одним злит других —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)

    check(all(v == 0 for v in F.all_of(p).values()), "новичок никому не свой")

    F.award(store, p, "undead_slain")
    check(F.value(p, "guard") > 0, "стража ценит упокоенную нежить")
    check(F.value(p, "scavengers") >= 0, "падальщики нейтральны к убийству нежити")
    check(F.value(p, "order") > 0, "орден тоже ценит упокоенную нежить")

    guard_before = F.value(p, "guard")
    order_before = F.value(p, "order")
    F.award(store, p, "grave_looted")
    check(F.value(p, "scavengers") > 0, "падальщики ценят мародёрство")
    check(F.value(p, "cult") < 0, "культ за это злится (из-за соперничества)")
    check(F.value(p, "order") < order_before, "мародёрство не в чести у ордена")

    check(F.RIVALS["guard"] == "scavengers" and F.RIVALS["scavengers"] == "cult"
          and F.RIVALS["cult"] == "guard" and F.RIVALS["order"] == "cult",
          "фракции связаны по кругу, у ордена свой враг — культ")


def test_ranks_and_side():
    print("\n— Звания и выбор стороны —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)

    check(F.rank(0)[1] == "Чужак", "ноль — чужак")
    check(F.rank(-150)[1] == "Враг", "глубокий минус — враг")
    check(F.rank(200)[1] == "Герой фракции", "высокая репутация — герой")

    check(F.allegiance(p) is None, "без очков стороны нет")
    p.reputation = {"guard": 100, "scavengers": 0, "cult": -40}
    check(F.allegiance(p) == "guard", "сторона — где больше всего очков")
    p.reputation = {"guard": 10, "scavengers": 5, "cult": 0}
    check(F.allegiance(p) is None, "мелкие очки стороной не делают")


def test_limits():
    print("\n— Потолок и дно —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    for _ in range(300):
        F.award(store, p, "undead_slain")
    check(F.value(p, "guard") <= F.MAX_REP, f"потолок: {F.value(p, 'guard')}")
    check(F.value(p, "cult") >= F.MIN_REP, f"дно: {F.value(p, 'cult')}")


def test_shop_discount():
    print("\n— Скидка в лавке —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)

    base = shop.price_for(p, 0)
    check(F.discount(p) == 0, "новичку скидки нет")

    p.reputation = {"guard": 1, "scavengers": 0, "cult": 0}
    check(F.discount(p) == 0,
          "одно очко ничего не меняет — скидка со звания «Знакомый»")

    p.reputation = {"guard": 300, "scavengers": 0, "cult": 0}
    check(F.discount(p) > 0, f"у героя фракции скидка {int(F.discount(p) * 100)}%")
    cheap = shop.price_for(p, 0)
    check(cheap < base, f"цена ниже: {cheap} против {base}")

    # Витрина, карточка и покупка обязаны показывать одну цену.
    p.gold = 10000
    card = game.handle(p, f"buyc:0")
    check(str(cheap) in card.text, "в карточке та же цена")
    before = p.gold
    game.handle(p, "buy:0")
    check(before - p.gold == cheap, "списано ровно столько, сколько показано")


def test_npc_reaction():
    print("\n— Жители реагируют —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)

    p.reputation = {"guard": 100, "scavengers": 0, "cult": 0}
    r = game.handle(p, "talk:0")
    check("Союзник" in r.text or "рады" in r.text, "к союзнику приветливы")

    p.reputation = {"guard": -120, "scavengers": 50, "cult": 0}
    check(F.refuses(p, 0), "враг стражи получает отказ")
    r = game.handle(p, "talk:0")
    check("Уходи" in r.text, "и это видно в диалоге")

    scav = next(i for i in range(len(data.NPCS))
                if F.npc_faction(i) == "scavengers")
    check(not F.refuses(p, scav), "у падальщиков тот же герой в почёте")
    r = game.handle(p, f"talk:{scav}")
    check(data.NPCS[scav][0] in r.text, "и с ними можно говорить")


def test_cataclysm_influence():
    print("\n— Настроения влияют на бедствия —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)

    check(F.cataclysm_mult(store) == 1.0, "без перевеса — обычная частота")

    p.reputation = {"guard": 0, "scavengers": 0, "cult": 200}
    check(F.cataclysm_mult(store) > 1, "культисты торопят конец света")

    p.reputation = {"guard": 200, "scavengers": 0, "cult": 0}
    check(F.cataclysm_mult(store) < 1, "стража отдаляет беды")

    p.reputation = {"guard": 100, "scavengers": 0, "cult": 100}
    check(F.cataclysm_mult(store) == 1.0, "равновесие возвращает норму")


def test_deeds_from_gameplay():
    print("\n— Репутация растёт от игры —")
    random.seed(6)
    store = fresh()
    game = Game(store)
    p = hero(store, game)

    cell = next(c for c in store.world.values() if c.mob >= 0)
    p.loc, p.x, p.y = cell.loc, cell.x, cell.y
    combat.start(p, cell.mob, store=store)
    for _ in range(20):
        if not p.combat:
            break
        combat.action(p, "hit", store.world, store)
    check(any(v != 0 for v in F.all_of(p).values()), "бой меняет репутацию")

    q = hero(store, game, 2, "Мара")
    death.bury(store, q, 100)
    p.loc, p.x, p.y = q.loc, q.x, q.y
    scav_before = F.value(p, "scavengers")
    game.handle(p, "claim")
    check(F.value(p, "scavengers") > scav_before,
          "мародёрство замечено падальщиками")


def test_screen_and_persistence():
    print("\n— Экран и сохранение —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    p.reputation = {"guard": 120, "scavengers": -20, "cult": -60}

    r = game.handle(p, "rep")
    check("Репутация" in r.text, "экран открывается")
    check(all(F.FACTIONS[k][1] in r.text for k in F.FACTIONS),
          "показаны все четыре силы")
    check("Твоя сторона" in r.text, "названа сторона игрока")
    check(any("rep" == b[1] for row in game.handle(p, "menu").keyboard
              for b in row), "кнопка есть в меню")

    store.save_player(p)
    again = Store(store.backend)
    check(F.value(again.players[p.tg_id], "guard") == 120,
          "репутация пережила перезагрузку")


def test_old_saves():
    print("\n— Старые сохранения —")
    backend = MemoryStorage()
    store = Store(backend)
    game = Game(store)
    p = hero(store, game)
    store.save()

    raw = json.loads(backend.get("shadowlands"))
    for pl in raw["players"].values():
        pl.pop("reputation", None)
    backend.set("shadowlands", json.dumps(raw, ensure_ascii=False))

    again = Store(backend)
    q = again.players[p.tg_id]
    check(F.all_of(q) == {k: 0 for k in F.FACTIONS}, "репутация создана нулевой")
    game2 = Game(again)
    for cmd in ("rep", "menu", "world", "shop", "talk:0"):
        try:
            game2.handle(q, cmd)
            check(True, f"экран «{cmd}» открывается")
        except Exception as e:
            check(False, f"экран «{cmd}» → {type(e).__name__}: {e}")


def test_panel():
    print("\n— Панель —")
    from webapp.pages import world as page_world

    store = fresh()
    game = Game(store)
    p = hero(store, game, 1, "Гидеон")
    p.reputation = {"guard": 150, "scavengers": 0, "cult": -50}

    class Ctx:
        pass

    ctx = Ctx()
    ctx.store = store
    ctx.state = {"loc": 0, "world_tab": "living", "cell_pick": ""}
    try:
        markup = page_world.render(ctx)
        check("Фракции и репутация" in markup, "блок фракций нарисован")
        check("Стража Погоста" in markup, "силы перечислены")
        check("Гидеон" in markup, "герой в таблице сторон")
    except Exception as e:
        check(False, f"вкладка «Жизнь мира» → {type(e).__name__}: {e}")


def main():
    for fn in (test_opposing_interests, test_ranks_and_side, test_limits,
               test_shop_discount, test_npc_reaction,
               test_cataclysm_influence, test_deeds_from_gameplay,
               test_screen_and_persistence, test_old_saves, test_panel):
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
