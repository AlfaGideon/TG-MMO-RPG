"""Перенос в браузерный стек: разбор, призрачный прах, Зал Славы.

Запуск: python3 tests/test_engine_legends.py

Раздел 2 `IDEAS-100.md` (пункты 12, 17, 34). У этих механик разное
хранилище: сервер держит записи в БД, браузерный стек — в
`store.settings`. Поэтому общими сделаны **правила и тексты**, а не код
доступа к данным: таблица выхода материалов, витрина призрака и вёрстка
Зала Славы теперь живут в `engine/` и используются обоими стеками.

Отдельно проверяется, что рекорд именной и **не перезаписывается** —
иначе «первый победитель» терял бы смысл.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import death, legends, salvage, spectral
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
    random.seed(6)
    store = Store(MemoryStorage())
    game = Game(store)

    print("\n— Разбор: выход растёт с редкостью и заточкой —")
    common = salvage.yield_for("common")
    rare = salvage.yield_for("rare")
    legendary = salvage.yield_for("legendary")
    check(common["iron_scrap"] < rare["iron_scrap"] < legendary["iron_scrap"],
          f"лом по редкости: {common['iron_scrap']} < {rare['iron_scrap']} "
          f"< {legendary['iron_scrap']}")
    check(common["magic_dust"] == 0 and rare["magic_dust"] == 1,
          "пыль падает только с редких и выше")
    check(salvage.yield_for("rare", 4)["steel_bars"] == 2,
          "заточка +4 даёт два слитка")
    check(salvage.yield_for("rare", 2)["iron_scrap"] >
          salvage.yield_for("rare", 0)["iron_scrap"],
          "заточка добавляет лома")
    check(salvage.yield_for("выдуманная")["iron_scrap"]
          == salvage.SCRAP_BY_RARITY["common"],
          "неизвестная редкость падает в common")

    class _Enum:
        value = "epic"
    check(salvage.yield_for(_Enum())["iron_scrap"]
          == salvage.SCRAP_BY_RARITY["epic"],
          "редкость-Enum сервера тоже понимается")
    check("Ржавый лом" in salvage.yield_text(rare), "текст выхода собирается")

    print("\n— Прах предков: сбор у могилы —")
    p = Player(tg_id=1, cls="berserker")
    p.loc, p.x, p.y = 1, 4, 4
    store.save_player(p)
    check(spectral.ash_of(p) == 0, "праха нет")

    r = game.handle(p, "honor")
    check("нет могилы" in (r.alert or "").lower(), "без могилы прах не собрать")

    dead = Player(tg_id=2, cls="mage")
    dead.loc, dead.x, dead.y = 1, 4, 4
    death.bury(store, dead, 100)
    r = game.handle(p, "honor")
    check(spectral.ash_of(p) == spectral.ASH_PER_GRAVE,
          f"собрано {spectral.ASH_PER_GRAVE} праха")

    print("\n— Призрак торгует за прах, а не за золото —")
    r = game.handle(p, "ghostbuy:spec_ethereal_blade")
    check("не хватает" in (r.alert or "").lower(), "дорогой товар не по карману")
    check(game.handle(p, "ghostbuy:выдуманный").alert is not None,
          "несуществующий товар отклонён")

    p.soul_ash = 100
    mp_before = p.max_mp
    money_before = p.bronze
    game.handle(p, "ghostbuy:spec_ancestor_tear")
    tear = spectral.ware_by_key("spec_ancestor_tear")
    check(spectral.ash_of(p) == 100 - tear["cost_ash"],
          f"списан прах: осталось {spectral.ash_of(p)}")
    check(p.max_mp == mp_before + spectral.TEAR_MANA_BONUS,
          f"мана выросла: {mp_before} → {p.max_mp}")
    check(p.bronze == money_before, "монеты не тронуты — платят прахом")

    wounded = Player(tg_id=3, cls="rogue")
    wounded.soul_ash = 100
    death.wound(wounded)
    store.save_player(wounded)
    check(death.wounded(wounded), "герой ранен")
    game.handle(wounded, "ghostbuy:spec_wound_heal")
    check(not death.wounded(wounded), "свиток вылечил раны")

    print("\n— Зал Славы: рекорд именной и один раз —")
    fresh = Store(MemoryStorage())
    check("пока пуста" in legends.hall_text(legends.all_records(fresh)),
          "пустая летопись объясняет, что делать")

    hero = Player(tg_id=4, name="Гидеон", cls="berserker")
    rival = Player(tg_id=5, name="Соперник", cls="mage")
    check(legends.record_first(fresh, "boss:eater", "Первый победитель", hero) is True,
          "рекорд зафиксирован")
    check(legends.record_first(fresh, "boss:eater", "Первый победитель", rival) is False,
          "тот же рекорд второй раз не занять")
    text = legends.hall_text(legends.all_records(fresh))
    check("Гидеон" in text and "Соперник" not in text,
          "в летописи остался первопроходец, а не последний")
    check(legends.has_record(fresh, "boss:eater"), "рекорд ищется по ключу")

    # Летопись не растёт бесконечно.
    for i in range(legends.MAX_RECORDS + 10):
        legends.record_first(fresh, f"deed:{i}", f"Подвиг {i}", hero)
    check(len(legends.all_records(fresh)) <= legends.MAX_RECORDS,
          f"летопись обрезана до {legends.MAX_RECORDS}")

    print("\n— Экраны и меню —")
    datas = [d for row in game.menu(p).keyboard for _l, d in row]
    check("legends" in datas, "в меню есть Зал Славы")
    check("🏆" in game.handle(p, "legends").text, "экран Зала Славы открывается")
    check("Призрак" in game.handle(p, "ghost").text, "витрина призрака открывается")

    look = game.handle(p, "look")
    look_datas = [d for row in look.keyboard for _l, d in row]
    check("honor" in look_datas and "ghost" in look_datas,
          "у могилы предлагают почтить память и призрака")

    print("\n— Правила общие с сервером —")
    try:
        from core import legends as c_leg
        from core import salvage as c_salv
        from core import spectral as c_spec
        check(c_spec.SPECTRAL_WARES is spectral.SPECTRAL_WARES,
              "витрина призрака — тот же объект")
        check(c_salv.S is salvage, "разбор берёт таблицу из engine/salvage")
        check(c_leg.hall_of_legends_text([]) == legends.hall_text([]),
              "экран Зала Славы одинаков в обоих стеках")
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
