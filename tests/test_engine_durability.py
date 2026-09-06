"""🔩 Прочность снаряжения: износ, поломка, ремонт.

python3 tests/test_engine_durability.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import combat, craft, currency, death, durability, items, rules
from engine.game import Game
from engine.models import Player
from engine.storage import Store
from webapp.backend import MemoryStorage

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


def _story(store, p, idx):
    p.inventory.append(int(idx))
    store.save_player(p)
    return store


def main():
    random.seed(7)
    store = Store(MemoryStorage())
    game = Game(store)
    p = Player(tg_id=1, cls="warrior", level=3)
    p.inventory = []
    p.bronze = 0
    store.save_player(p)

    print("\n— Правила —")
    check(durability.is_gear({"type": "weapon"}) is True, "оружие — вещь с прочностью")
    check(durability.is_gear({"type": "consumable"}) is False,
          "расходник не изнашивается")
    check(durability.RULES["max"] == 100, "новая вещь имеет 100 прочности")
    check(durability.rarity_mult("legendary") > durability.rarity_mult("common"),
          "легендарку чинить дороже обычной")

    print("\n— Экземпляры —")
    weapon = items.create(store, 0, source="mob", owner=p.tg_id, luck=0)
    check(weapon is not None, "создаётся именной экземпляр оружия")
    check(weapon["durability"] == 100 and weapon["durability_max"] == 100,
          "у оружия есть полная прочность")
    potion = items.create(store, 29, source="shop", owner=p.tg_id, luck=0)
    check(potion is None, "расходники прочность не получают")

    print("\n— Экипировка и бой —")
    _story(store, p, 0)
    r = game.handle(p, "on:0")
    check(p.equipped.get("weapon") == 0, "оружие надето")
    uid = (getattr(p, "worn", None) or {}).get("weapon")
    check(uid == weapon["uid"], "worn помнит конкретный uid")
    inst = items.get(store, uid)
    check(durability.cur(inst) == 100, "надели исправную вещь")

    combat.start(p, 0, store=store)
    p.combat["mob_hp"] = 99999          # не убьём за один удар
    p.hp = 200
    game.handle(p, "fight:hit")
    check(durability.cur(items.get(store, uid)) == 99,
          "свой удар стачивает оружие на 1")

    armor = items.create(store, 10, source="mob", owner=p.tg_id, luck=0)
    _story(store, p, 10)
    game.handle(p, "on:1")
    armor_uid = (getattr(p, "worn", None) or {}).get("armor")
    check(armor_uid == armor["uid"], "броня надетa")
    p.hp = 200
    combat.start(p, 1, store=store)
    p.combat["mob_hp"] = 99999
    for _ in range(12):                    # моб может уклониться — ждём удар
        if durability.cur(items.get(store, armor_uid)) < 100:
            break
        p.hp = 200
        p.combat["mob_hp"] = 99999
        game.handle(p, "fight:hit")
    check(durability.cur(items.get(store, armor_uid)) == 99,
          "полученный удар стачивает защиту на 1")

    print("\n— Поломка отключает статы и блокирует надевание —")
    inst = items.get(store, uid)
    broken_weapon_st = rules.stats(p, store)
    inst["durability"] = 0
    broken_gear_st = rules.stats(p, store)
    # Снимаем сломанное и проверяем надевание второго экземпляра.
    game.handle(p, "off:0")
    r = game.handle(p, "on:0")
    check("сломана" in (r.alert or ""), "сломанное оружие нельзя надеть")
    check(broken_weapon_st["damage"] - broken_gear_st["damage"] >= 0,
          "поломка не прибавляет статов")
    inst["durability"] = 100
    game.handle(p, "on:0")
    healthy_st = rules.stats(p, store)
    check(healthy_st["damage"] > broken_gear_st["damage"],
          "починка возвращает статы")

    print("\n— Смерть треплет всё надетое —")
    weapon_before = durability.cur(items.get(store, uid))
    armor_before = durability.cur(items.get(store, armor_uid))
    inst["durability"] = 100
    game.handle(p, "on:0")
    death.defeat(store, p, "Тестовый моб")
    check(durability.cur(items.get(store, uid)) == 93,
          "оружие после смерти теряет 7")
    check(durability.cur(items.get(store, armor_uid)) == armor_before - 7,
          "броня после смерти теряет 7")

    print("\n— Ремонт —")
    inst = items.get(store, uid)
    missing = durability.max_of(inst) - durability.cur(inst)
    cost = durability.repair_cost(inst)
    craft.add_material(store, p.tg_id, 0, 2)
    currency.earn(p, 1000)
    view = game.handle(p, "repair:0")
    check("Починка" in view.text and items.title(inst) in view.text,
          "экран починки показывает изношенную вещь")
    before = durability.cur(inst)
    r = game.handle(p, f"repairing:{uid}")
    after = durability.cur(items.get(store, uid))
    check("починено" in (r.alert or "").lower(), "ремонт подтверждён")
    check(after == durability.max_of(inst) and after > before,
          "прочность вернулась к максимуму")
    check(missing >= 1 and cost >= 2, "цена положительная и соответствует износу")
    craft.add_material(store, p.tg_id, 0, 1)
    r = game.handle(p, f"repairing:{uid}")
    check("исправности" in (r.alert or ""), "исправную вещь не ремонтируют второй раз")

    print("\n— Карточка —")
    check("Прочность" in durability.card_line(inst), "карточка показывает прочность")
    inst["durability"] = 0
    check("сломано" in durability.card_line(inst), "сломанное видно в карточке")

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
