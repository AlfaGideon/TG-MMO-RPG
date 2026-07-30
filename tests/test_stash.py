"""Два инвентаря: сумка теряется, защищённый карман — нет. VIP его расширяет.

python3 tests/test_stash.py
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import combat, death, stash
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
    p.loc, p.x, p.y = 0, 5, 5            # Погост — безопасно
    return p


def kill(store, p):
    """Гарантированно убить героя Пожирателем."""
    p.hp, p.max_hp, p.strength = 1, 100, 1
    p.loc, p.x, p.y = 1, 3, 3
    r = combat.start(p, 6, store=store)
    for _ in range(10):
        if not p.combat:
            break
        r = combat.action(p, "hit", store.world, store)
    return r


# ── размер и VIP ────────────────────────────────────────────

def test_capacity_and_vip():
    print("\n— Размер кармана и VIP —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)

    check(stash.capacity(p) == stash.SLOTS, f"базовый размер {stash.SLOTS}")
    check(stash.capacity(p) < 50, "карман меньше безразмерной сумки")

    stash.grant_vip(p, 7)
    check(stash.is_vip(p), "VIP активен")
    check(stash.capacity(p) == stash.SLOTS + stash.VIP_BONUS,
          f"VIP расширил до {stash.capacity(p)}")
    check(stash.vip_left_days(p) == 7, "срок VIP виден")

    stash.revoke_vip(p)
    check(not stash.is_vip(p) and stash.capacity(p) == stash.SLOTS,
          "после отзыва карман прежний")

    # Истёкший VIP не считается активным.
    import time as _t
    p.is_vip, p.vip_until = True, _t.time() - 10
    check(not stash.is_vip(p), "просроченный VIP не действует")
    p.is_vip, p.vip_until = True, 0
    check(stash.is_vip(p) and stash.vip_left_days(p) == 0, "бессрочный VIP работает")


def test_vip_persists():
    print("\n— VIP переживает перезагрузку —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    stash.grant_vip(p, 7)
    store.save()

    again = Store(store.backend)
    q = again.players[p.tg_id]
    check(stash.is_vip(q), "статус сохранён")
    check(stash.capacity(q) == stash.SLOTS + stash.VIP_BONUS,
          "и карман остался расширенным")


# ── перекладывание ──────────────────────────────────────────

def test_move_items():
    print("\n— Перекладывание вещей —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    p.inventory = [0, 1, 2, 3, 4, 5, 6, 7]

    game.handle(p, "stput:0")
    check(len(p.stash) == 1 and len(p.inventory) == 7, "вещь ушла в карман")

    for _ in range(stash.SLOTS - 1):
        game.handle(p, "stput:0")
    check(len(p.stash) == stash.SLOTS, f"карман заполнен: {len(p.stash)}")

    r = game.handle(p, "stput:0")
    check(bool(r.alert) and "полон" in r.alert, "сверх лимита не влезает")

    n = len(p.inventory)
    game.handle(p, "stake:0")
    check(len(p.inventory) == n + 1 and len(p.stash) == stash.SLOTS - 1,
          "вещь вернулась в сумку")


def test_safe_zone_only():
    print("\n— Только в безопасных землях —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    p.inventory = [0, 1]
    p.stash = [2]

    p.loc = 1                                    # Тёмный Лес
    check(not stash.safe_here(p), "в опасной локации карман закрыт")
    check(bool(game.handle(p, "stput:0").alert), "убрать нельзя")
    check(bool(game.handle(p, "stake:0").alert), "достать нельзя")
    check("только в безопасных" in game.handle(p, "stash").text,
          "экран объясняет, почему")

    p.loc = 0
    check(stash.safe_here(p), "в Погосте карман открыт")
    # Успех тоже возвращает alert («в карман: …»), поэтому смотрим на факт.
    n = len(p.stash)
    game.handle(p, "stput:0")
    check(len(p.stash) == n + 1, "здесь перекладывать можно")


def test_equipped_unequips():
    print("\n— Надетое снимается при уборке —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    p.inventory = [0]
    p.equipped = {"weapon": 0}

    game.handle(p, "stput:0")
    check(p.equipped.get("weapon") is None, "спрятанное больше не надето")
    check(p.stash == [0], "вещь в кармане")


# ── потери при гибели ───────────────────────────────────────

def test_death_keeps_stash():
    print("\n— Смерть: карман цел, сумка редеет —")
    random.seed(4)
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    p.inventory = [0, 1, 2, 3, 4, 5]
    p.stash = [7, 8]
    p.gold = 500
    p.equipped = {}
    bag_before, stash_before = list(p.inventory), list(p.stash)

    r = kill(store, p)
    check(len(p.inventory) < len(bag_before),
          f"из сумки выпало: {len(bag_before)} → {len(p.inventory)}")
    check(p.stash == stash_before, "карман не тронут")
    check("карман" in r.text.lower(), "игроку сказано про карман")

    g = death.mine(store, p)
    check(g is not None and g.get("items"), "выпавшее лежит в могиле")
    check(len(g["items"]) == len(bag_before) - len(p.inventory),
          "в могиле ровно то, что потерялось")


def test_death_keeps_worn():
    print("\n— Надетое с трупа не снимают —")
    random.seed(11)
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    p.inventory = [0, 1, 2, 3]
    p.equipped = {"weapon": 0}
    p.gold = 100

    kill(store, p)
    check(0 in p.inventory, "надетое оружие осталось при герое")


def test_return_for_goods():
    print("\n— Возврат за вещами —")
    random.seed(4)
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    p.inventory = [0, 1, 2, 3]
    p.gold = 200
    p.equipped = {}
    kill(store, p)

    g = death.mine(store, p)
    goods = len(g.get("items") or [])
    gold = g["gold"]
    n_before, gold_before = len(p.inventory), p.gold

    p.loc, p.x, p.y = g["loc"], g["x"], g["y"]
    r = game.handle(p, "claim")
    check(len(p.inventory) == n_before + goods, "вещи вернулись все до одной")
    check(p.gold == gold_before + gold, "и золото тоже")
    check("вещей" in r.text, "в отчёте перечислено")
    check(death.mine(store, p) is None, "могила исчезла")


def test_looting_stranger():
    print("\n— Чужая могила: половина праха —")
    store = fresh()
    game = Game(store)
    a = hero(store, game, 1, "Гидеон")
    b = hero(store, game, 2, "Мара")

    b.loc, b.x, b.y = 1, 7, 7
    death.bury(store, b, 100, [0, 1, 2, 3])
    a.loc, a.x, a.y = 1, 7, 7
    n_before, gold_before = len(a.inventory), a.gold

    r = game.handle(a, "claim")
    check(a.gold - gold_before == 50, "золота досталась половина")
    check(len(a.inventory) - n_before == 2, "вещей тоже половина")
    check("прах" in r.text, "объяснено, почему половина")


# ── совместимость ───────────────────────────────────────────

def test_old_saves():
    print("\n— Старые сохранения без кармана —")
    backend = MemoryStorage()
    store = Store(backend)
    game = Game(store)
    p = hero(store, game)
    p.inventory = [0, 1]
    store.save()

    raw = json.loads(backend.get("shadowlands"))
    for pl in raw["players"].values():           # выкидываем новые поля
        for key in ("stash", "is_vip", "vip_until"):
            pl.pop(key, None)
    backend.set("shadowlands", json.dumps(raw, ensure_ascii=False))

    again = Store(backend)
    q = again.players[p.tg_id]
    check(getattr(q, "stash", None) == [], "карман создан пустым")
    check(not stash.is_vip(q), "VIP по умолчанию выключен")
    check(stash.capacity(q) == stash.SLOTS, "размер кармана обычный")

    game2 = Game(again)
    for cmd in ("bag", "stash", "profile", "world"):
        try:
            game2.handle(q, cmd)
            check(True, f"экран «{cmd}» открывается")
        except Exception as e:
            check(False, f"экран «{cmd}» → {type(e).__name__}: {e}")


def test_screens():
    print("\n— Экраны —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    p.inventory = [0, 1]

    bag = game.handle(p, "bag")
    check("карман" in bag.text.lower(), "в сумке виден счётчик кармана")
    check(any("stash" in b[1] for row in bag.keyboard for b in row),
          "есть кнопка перехода в карман")

    card = game.handle(p, "it:0")
    check(any("stput" in b[1] for row in card.keyboard for b in row),
          "в карточке есть «убрать в карман»")

    view = game.handle(p, "stash")
    check("Защищённый карман" in view.text, "экран кармана открывается")
    check("VIP" in view.text, "не-VIP видит подсказку про расширение")

    prof = game.handle(p, "profile")
    check("Карман" in prof.text, "в профиле виден размер кармана")
    stash.grant_vip(p, 5)
    check("👑" in game.handle(p, "profile").text, "у VIP корона в профиле")


def test_panel():
    print("\n— Панель —")
    from webapp.pages import players as page_players

    store = fresh()
    game = Game(store)
    p = hero(store, game)
    p.stash = [0, 1]
    stash.grant_vip(p, 30)

    class Ctx:
        pass

    ctx = Ctx()
    ctx.store = store
    ctx.state = {}
    try:
        markup = page_players.edit_form(ctx, p.tg_id)
        check("Защищённый карман" in markup, "карман показан в карточке")
        check("player-vip" in markup, "есть кнопка управления VIP")
        check("активен" in markup, "статус VIP виден")
    except Exception as e:
        check(False, f"карточка игрока → {type(e).__name__}: {e}")


def main():
    for fn in (test_capacity_and_vip, test_vip_persists, test_move_items,
               test_safe_zone_only, test_equipped_unequips,
               test_death_keeps_stash, test_death_keeps_worn,
               test_return_for_goods, test_looting_stranger,
               test_old_saves, test_screens, test_panel):
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
