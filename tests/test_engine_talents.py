"""Перенос в браузерный стек: таланты, подклассы, фамильяры.

Запуск: python3 tests/test_engine_talents.py

Раздел 2 `IDEAS-100.md` (пункты 19, 22, 23). Механики жили только на
сервере — на GitHub Pages их не было вовсе. Каталоги перенесены в
`engine/`, а `core/*` стали реэкспортом, поэтому разойтись стекам нечем.

Отдельно проверяется, что бонусы реально влияют на статы, а очки талантов
начисляются по уровню и не теряются при скачке.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import currency, familiars, rules, subclasses, talents
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
    random.seed(9)
    store = Store(MemoryStorage())
    game = Game(store)

    print("\n— Очки талантов начисляются по уровню —")
    p = Player(tg_id=1, cls="berserker")
    store.save_player(p)
    check((p.talent_points or 0) == 0, "на первом уровне очков нет")
    rules.add_exp(p, 1000)
    expected = talents.points_for_level(p.level)
    check(p.talent_points == expected,
          f"ур.{p.level} → очков {p.talent_points} = {expected}")

    # Скачок через несколько уровней не должен «съедать» очки.
    jumper = Player(tg_id=2, cls="berserker")
    rules.add_exp(jumper, 100_000)
    check(jumper.talent_points == talents.points_for_level(jumper.level),
          f"после скачка до ур.{jumper.level}: очков {jumper.talent_points}")

    print("\n— Зажигание звезды и её бонусы —")
    hero = Player(tg_id=3, cls="berserker")
    store.save_player(hero)
    res = talents.unlock_talent(hero, "star_wrath")
    check(res["ok"] is False and "очков" in res["reason"],
          "без очков звезда не зажигается")

    hero.talent_points = 2
    dmg_before = rules.stats(hero, store)["damage"]
    res = talents.unlock_talent(hero, "star_wrath")
    check(res["ok"] is True, "звезда зажжена")
    check(hero.talent_points == 1, "очко списано")
    check(rules.stats(hero, store)["damage"] == dmg_before + 15,
          f"урон вырос: {dmg_before} → {rules.stats(hero, store)['damage']}")
    check(talents.unlock_talent(hero, "star_wrath")["ok"] is False,
          "повторно ту же звезду зажечь нельзя")
    check(talents.unlock_talent(hero, "выдуманная")["ok"] is False,
          "несуществующая звезда отклонена")

    hp_before = hero.max_hp
    talents.unlock_talent(hero, "star_fortitude")
    check(hero.max_hp == hp_before + 50, "звезда стойкости подняла максимум HP")
    check(hero.current_hp if hasattr(hero, "current_hp") else hero.hp,
          "здоровье не обнулилось")

    broken = Player(tg_id=4, cls="mage")
    broken.talents_json = "{битый"
    check(talents.get_unlocked_talents(broken) == [],
          "битый JSON талантов читается как пусто")

    print("\n— Подкласс: порог, единственность, множители —")
    warrior = Player(tg_id=5, cls="warrior")
    warrior.level = 5
    store.save_player(warrior)
    check(subclasses.choose_subclass(warrior, "berserker")["ok"] is False,
          f"до {subclasses.SUBCLASS_MIN_LEVEL} уровня путь закрыт")

    warrior.level = subclasses.SUBCLASS_MIN_LEVEL
    check(subclasses.choose_subclass(warrior, "выдуманный")["ok"] is False,
          "неизвестный подкласс отклонён")
    check(subclasses.choose_subclass(warrior, "berserker")["ok"] is True,
          "путь выбран")
    check(warrior.subclass == "berserker", "подкласс записан герою")

    avail = subclasses.get_available_subclasses("warrior")
    check(all(s["class_base"] == "warrior" for s in avail),
          "воину предлагают только его пути")

    # Множитель урона подкласса виден в статах.
    plain = Player(tg_id=6, cls="warrior")
    plain.level = 12
    idx = next(i for i, t in enumerate(__import__("engine.data", fromlist=["d"]).ITEMS)
               if t[1] == "weapon" and t[5].get("damage"))
    for h in (plain, warrior):
        h.inventory.append(idx)
        h.equipped["weapon"] = idx
    # Множитель подкласса применяется к полному урону в attack_roll (как на
    # сервере), поэтому сравниваем реальные удары, а не бонус экипировки.
    check(rules.stats(warrior, store)["damage_mult"] > 1.0,
          "у берсерка есть множитель урона")
    check(rules.stats(plain, store)["damage_mult"] == 1.0,
          "у героя без пути множителя нет")
    random.seed(1)
    base_hits = [rules.attack_roll(plain, 0, store)[0] for _ in range(40)]
    random.seed(1)
    berserk_hits = [rules.attack_roll(warrior, 0, store)[0] for _ in range(40)]
    avg_base = sum(base_hits) / len(base_hits)
    avg_bers = sum(berserk_hits) / len(berserk_hits)
    check(avg_bers > avg_base,
          f"берсерк бьёт сильнее: {avg_bers:.1f} > {avg_base:.1f}")

    print("\n— Фамильяр: покупка за бронзу и бонусы —")
    tamer = Player(tg_id=7, cls="ranger")
    tamer.bronze, tamer.silver, tamer.gold = 0, 0, 0
    store.save_player(tamer)
    check(familiars.get_familiar(tamer) is None, "спутника нет")
    check(familiars.set_familiar(tamer, "выдуманный") is False,
          "несуществующий спутник не приручается")

    r = game.handle(tamer, "famgo:crow")
    check("хватает" in (r.alert or "").lower(), "без денег спутника не дают")

    currency.earn(tamer, familiars.FAMILIARS["crow"]["cost"])
    before = currency.total(tamer)
    r = game.handle(tamer, "famgo:crow")
    check(getattr(tamer, "familiar_type", "") == "crow", "спутник приручён")
    check(currency.total(tamer) == before - familiars.FAMILIARS["crow"]["cost"],
          "деньги списаны ровно по цене")
    check(familiars.familiar_bonuses(tamer)["crit_bonus"] > 0,
          "бонус спутника считается")
    r = game.handle(tamer, "famgo:hound")
    check("уже есть" in (r.alert or "").lower(), "второго спутника не завести")

    print("\n— Экраны и меню —")
    menu = game.menu(p)
    datas = [d for row in menu.keyboard for _l, d in row]
    for cb in ("talents", "subclass", "familiar"):
        check(cb in datas, f"в меню есть «{cb}»")
    check("Звёздное древо" in game.handle(hero, "talents").text,
          "экран созвездий открывается")
    check("Специализация" in game.handle(warrior, "subclass").text,
          "экран пути открывается")
    check("Фамильяр" in game.handle(tamer, "familiar").text,
          "экран спутника открывается")

    print("\n— Каталоги общие с сервером —")
    try:
        from core import familiars as c_fam
        from core import subclasses as c_subs
        from core import talents as c_tal
        check(c_tal.TALENT_STARS is talents.TALENT_STARS, "древо талантов — тот же объект")
        check(c_subs.SUBCLASSES is subclasses.SUBCLASSES, "подклассы — тот же объект")
        check(c_fam.FAMILIARS is familiars.FAMILIARS, "фамильяры — тот же объект")
    except ImportError as e:
        check(True, f"серверный стек недоступен, пропуск ({e})")

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
