"""Перенос в браузерный стек: титулы, бестиарий, луна, перерождение.

Запуск: python3 tests/test_engine_progress.py

Раздел 2 `IDEAS-100.md` (пункты 16, 21, 24, 32): эти механики жили только
на сервере, в `engine/` их не было — на GitHub Pages они физически не
появлялись, потому что туда грузится лишь то, что перечислено в
`modules.json`.

Проверяется не только работа в движке, но и то, что каталоги **общие**:
`core/*` реэкспортируют `engine/*`, поэтому разойтись они не могут.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import bestiary, combat, data, lunar, prestige, rules, titles
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
    random.seed(5)
    store = Store(MemoryStorage())
    game = Game(store)

    print("\n— Титулы: открытие, ношение, бонусы —")
    p = Player(tg_id=1, cls="berserker")
    store.save_player(p)
    check(titles.get_unlocked_titles(p) == [], "новых титулов нет")
    check(titles.set_active_title(p, "Убийца Левиафана") is False,
          "нельзя надеть неоткрытый титул")
    check(titles.unlock_title(p, "Выдуманный титул") is False,
          "несуществующий титул не открывается")

    check(titles.unlock_title(p, "Убийца Левиафана") is True, "титул открыт")
    check(titles.unlock_title(p, "Убийца Левиафана") is False,
          "повторно тот же титул не открывается")

    dmg_before = rules.stats(p, store)["damage"]
    check(titles.set_active_title(p, "Убийца Левиафана") is True, "титул надет")
    dmg_after = rules.stats(p, store)["damage"]
    check(dmg_after == dmg_before + 5,
          f"бонус титула в статах: {dmg_before} → {dmg_after}")
    check("Убийца Левиафана" in titles.title_line(p), "строка титула собрана")

    hp_before = rules.stats(p, store)["max_hp"]
    titles.unlock_title(p, "Несущий Свет")
    titles.set_active_title(p, "Несущий Свет")
    check(rules.stats(p, store)["max_hp"] == hp_before + 20,
          "титул на здоровье тоже работает")
    check(rules.stats(p, store)["damage"] == dmg_before,
          "бонус прошлого титула снят — носится только один")

    titles.set_active_title(p, "none")
    check(rules.stats(p, store)["damage"] == dmg_before, "титул снят")

    print("\n— Битое поле титулов не роняет профиль —")
    broken = Player(tg_id=2, cls="mage")
    broken.unlocked_titles_json = "{не json"
    check(titles.get_unlocked_titles(broken) == [], "битый JSON читается как пусто")

    print("\n— Бестиарий: счёт побед и потолок бонуса —")
    hunter = Player(tg_id=3, cls="berserker")
    check(bestiary.get_mob_slayer_bonus(hunter, "Ворг") == 1.0, "без побед бонуса нет")
    for _ in range(bestiary.KILLS_PER_STEP):
        bestiary.record_kill(hunter, "Ворг")
    check(bestiary.slayer_pct(hunter, "Ворг") == 1,
          f"{bestiary.KILLS_PER_STEP} побед → +1 %")
    check(bestiary.get_mob_slayer_bonus(hunter, "Скелет") == 1.0,
          "виды считаются раздельно")
    for _ in range(bestiary.KILLS_PER_STEP * bestiary.MAX_BONUS_PCT * 2):
        bestiary.record_kill(hunter, "Ворг")
    check(bestiary.slayer_pct(hunter, "Ворг") == bestiary.MAX_BONUS_PCT,
          f"потолок +{bestiary.MAX_BONUS_PCT} % соблюдён")
    check("Ворг" in bestiary.bestiary_card_text(hunter), "атлас показывает вид")

    print("\n— Бестиарий пополняется в бою —")
    fighter = Player(tg_id=4, cls="berserker")
    fighter.loc, fighter.x, fighter.y = 1, 3, 3
    store.save_player(fighter)
    mob_name = data.MOBS[1][0]
    combat.start(fighter, 1, store=store)
    guard = 0
    while fighter.combat and guard < 200:
        combat.action(fighter, "hit", store.world, store)
        guard += 1
    check(bestiary.get_bestiary(fighter).get(mob_name, 0) >= 1,
          f"победа над «{mob_name}» записана в атлас")

    print("\n— Луна: расчёт, каталог и заморозка —")
    seen = {lunar.get_current_lunar_phase(h * 3600)["key"]
            for h in range(lunar.CYCLE_DURATION_HOURS)}
    check(len(seen) == len(lunar.PHASES), "за сутки проходят все фазы")
    natural = lunar.phase_of(store)
    other = next(x for x in lunar.PHASES if x["key"] != natural["key"])
    lunar.set_override(store, other["key"])
    check(lunar.phase_of(store)["key"] == other["key"], "фаза заморожена")
    lunar.set_override(store, "")
    check(lunar.phase_of(store)["key"] == lunar.get_current_lunar_phase()["key"],
          "естественный цикл возвращён")
    bad = False
    try:
        lunar.set_override(store, "выдуманная_фаза")
    except ValueError:
        bad = True
    check(bad, "неизвестная фаза отклонена")

    print("\n— Перерождение: порог и прибавка —")
    veteran = Player(tg_id=5, cls="berserker")
    veteran.level, veteran.strength = 5, 20
    store.save_player(veteran)
    check(prestige.can_rebirth(veteran)[0] is False, "новичку ритуал недоступен")
    check(prestige.perform_rebirth(veteran, store)["ok"] is False,
          "и не срабатывает в обход проверки")

    veteran.level = prestige.REBIRTH_MIN_LEVEL
    veteran.exp = 500
    str_before = veteran.strength
    res = prestige.perform_rebirth(veteran, store)
    check(res["ok"] is True, "ритуал совершён")
    check(veteran.level == 1 and veteran.exp == 0, "уровень и опыт обнулены")
    check(veteran.rebirth_count == 1, "круг засчитан")
    check(veteran.strength > str_before,
          f"Искра Бессмертия подняла силу: {str_before} → {veteran.strength}")
    check(veteran.hp == veteran.max_hp, "здоровье восстановлено")

    print("\n— Экраны и меню движка —")
    menu = game.menu(p)
    datas = [d for row in menu.keyboard for _l, d in row]
    check("bestiary" in datas and "titles" in datas,
          "в меню есть бестиарий и титулы")
    check("📖" in game.handle(p, "bestiary").text, "экран бестиария открывается")
    check("Титулы" in game.handle(p, "titles").text, "экран титулов открывается")
    check("Перерождение" in game.handle(veteran, "rebirth").text,
          "экран перерождения открывается")

    titles.unlock_title(p, "Мастер Кузницы")
    r = game.handle(p, "title:Мастер Кузницы")
    check(getattr(p, "active_title", "") == "Мастер Кузницы",
          "титул надевается из меню")
    check("надет" in (r.alert or "").lower(), "игроку сказали о смене титула")

    print("\n— Каталоги общие с сервером —")
    try:
        from core import bestiary as c_bestiary
        from core import lunar as c_lunar
        from core import prestige as c_prestige
        from core import titles as c_titles
        check(c_titles.TITLES_CATALOG is titles.TITLES_CATALOG,
              "каталог титулов — тот же объект")
        check(c_lunar.PHASES is lunar.PHASES, "каталог фаз — тот же объект")
        check(c_bestiary.record_kill is bestiary.record_kill,
              "бестиарий — та же функция")
        check(c_prestige.REBIRTH_MIN_LEVEL == prestige.REBIRTH_MIN_LEVEL,
              "порог перерождения совпадает")
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
