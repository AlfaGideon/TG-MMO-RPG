"""Долг A: экипировка помнит КОНКРЕТНУЮ вещь, а не «такую же».

Запуск: python3 tests/test_slot_identity.py

Из `AUDIT-BUGS.md`, раздел A: `p.inventory` хранит индексы шаблонов, и
`p.equipped[slot]` хранил индекс — две одинаковые вещи были неразличимы:

  * продажа/прятание **второй копии** надетой вещи снимала экипировку;
  * дубликат надетой вещи **не выпадал** в надгробие при смерти.

Оба сценария воспроизводятся ниже «до и после»: сначала проверяется, что
старая логика сравнения по индексу действительно ошибалась, затем — что
новая (`engine/slots.py`, позиция вещи в сумке) отвечает верно.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import data, inventory, items, rules, shop, slots, stash
from engine.models import Player
from engine.storage import Store
from webapp.backend import MemoryStorage

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


def _weapon_idx():
    return next(i for i, t in enumerate(data.ITEMS) if t[1] == "weapon")


def _hero(store, tg_id=1):
    p = Player(tg_id=tg_id, cls="berserker")
    store.save_player(p)
    return p


def main():
    random.seed(11)
    store = Store(MemoryStorage())
    w = _weapon_idx()

    print("\n— Две одинаковые вещи различимы —")
    p = _hero(store, 1)
    p.inventory.extend([w, w])          # две копии одного меча
    inventory.equip(p, 0, store)        # надета ПЕРВАЯ
    check(slots.is_equipped_at(p, 0), "первая копия помечена надетой")
    check(not slots.is_equipped_at(p, 1), "вторая копия не считается надетой")
    # Старая логика сравнивала по индексу шаблона и путала копии:
    check(p.equipped.get("weapon") == p.inventory[1],
          "проверка по индексу шаблона (старый способ) обе копии считает одним")

    print("\n— Продажа второй копии не снимает экипировку (баг A1) —")
    before_dmg = rules.stats(p, store)["damage"]
    r = inventory.sell(p, 1, store)
    check("Продано" in (r.alert or ""), "вторая копия продана")
    check(p.equipped.get("weapon") == w, "экипировка осталась на месте")
    check(len(p.inventory) == 1 and slots.is_equipped_at(p, 0),
          "надетая вещь осталась в сумке и помечена верно")
    check(rules.stats(p, store)["damage"] == before_dmg,
          f"урон не просел: {rules.stats(p, store)['damage']} = {before_dmg}")

    print("\n— Продажа именно надетой вещи снимает слот —")
    p2 = _hero(store, 2)
    p2.inventory.extend([w, w])
    inventory.equip(p2, 1, store)       # надета ВТОРАЯ
    check(slots.is_equipped_at(p2, 1), "надета вторая копия")
    inventory.sell(p2, 1, store)        # продаём именно её
    check("weapon" not in p2.equipped, "слот освободился")
    check(len(p2.inventory) == 1, "в сумке осталась одна копия")
    check(not slots.is_equipped_at(p2, 0), "оставшаяся копия не «надета» сама собой")

    print("\n— Прятание копии в карман не раздевает героя —")
    p3 = _hero(store, 3)
    p3.loc = 0                           # Погост — безопасная зона
    p3.inventory.extend([w, w])
    inventory.equip(p3, 0, store)
    stash.put(p3, 1, store)
    check(p3.equipped.get("weapon") == w, "экипировка на месте после прятания копии")
    check(len(p3.inventory) == 1 and slots.is_equipped_at(p3, 0),
          "позиция надетой вещи не съехала")

    print("\n— Дубликат надетой вещи выпадает при смерти (баг A2) —")
    p4 = _hero(store, 4)
    p4.inventory.extend([w, w, w])
    inventory.equip(p4, 0, store)
    losable = [i for i in range(len(p4.inventory))
               if i not in slots.equipped_positions(p4)]
    check(losable == [1, 2],
          f"терять можно только ненадетые копии: {losable}")
    lost = stash.drop_on_death(p4, rng=random.Random(3), store=store)
    check(lost, f"что-то выпало в надгробие: {len(lost)} шт.")
    check(p4.equipped.get("weapon") == w, "надетая вещь уцелела")
    check(slots.is_equipped_at(p4, p4.inventory.index(w)),
          "позиция надетой вещи пересчитана после потерь")

    print("\n— Позиции переживают удаление вещей слева —")
    p5 = _hero(store, 5)
    other = next(i for i, t in enumerate(data.ITEMS)
                 if t[1] == "armor")
    p5.inventory.extend([other, w])
    inventory.equip(p5, 1, store)        # надет меч на позиции 1
    slots.take_at(p5, 0)                 # убрали броню слева
    check(slots.equipped_positions(p5) == {0},
          "позиция сдвинулась на 0 вместе с вещью")
    check(slots.is_equipped_at(p5, 0) and p5.inventory[0] == w,
          "надетым остался тот же меч")

    print("\n— Именной экземпляр остаётся привязан к своей копии —")
    p6 = _hero(store, 6)
    inst_a = items.create(store, w, source="mob", owner=p6.tg_id, luck=0)
    inst_a["stats"] = {"damage": 41}
    p6.inventory.extend([w, w])
    inventory.equip(p6, 0, store)
    check(p6.worn.get("weapon") == inst_a["uid"], "uid экземпляра записан")
    check(rules.stats(p6, store)["damage"] == 41,
          "в бою считаются статы именно этого экземпляра")
    inventory.sell(p6, 1, store)         # продаём вторую копию
    check(p6.worn.get("weapon") == inst_a["uid"], "uid не потерялся")
    check(rules.stats(p6, store)["damage"] == 41,
          "урон после продажи копии не изменился")

    print("\n— Старые сохранения чинятся автоматически —")
    old = Player.from_dict({"tg_id": 7, "cls": "berserker",
                            "inventory": [w, w], "equipped": {"weapon": w}})
    check(not getattr(old, "equipped_pos", None), "в старом сейве позиций нет")
    slots.sync_positions(old)
    check(slots.equipped_positions(old) == {0},
          "позиция восстановлена по индексу")
    # Надетая вещь пропала из сумки — слот снимается, а не висит призраком.
    broken = Player.from_dict({"tg_id": 8, "cls": "berserker",
                               "inventory": [], "equipped": {"weapon": w}})
    slots.sync_positions(broken)
    check("weapon" not in broken.equipped,
          "слот с отсутствующей вещью снят, бонусы не начисляются")

    print("\n— Лавка показывает «надето» у нужной копии —")
    p9 = _hero(store, 9)
    p9.inventory.extend([w, w])
    inventory.equip(p9, 1, store)
    text = shop.sell_list(p9, 0).text
    check(text.count("надето") == 1, "пометка «надето» ровно одна")

    print("\n— Изъятие по шаблону щадит надетое —")
    p10 = _hero(store, 10)
    p10.inventory.extend([w, w])
    inventory.equip(p10, 0, store)
    taken = slots.take_first_unequipped(p10, w)
    check(taken == 1, f"забрали ненадетую копию (позиция {taken})")
    check(p10.equipped.get("weapon") == w and len(p10.inventory) == 1,
          "герой остался экипирован")

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
