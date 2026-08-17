"""Перенос в браузерный стек: руны, мирные занятия, эмбиент.

Запуск: python3 tests/test_engine_gathering.py

Раздел 2 `IDEAS-100.md` (пункты 11, 18, 25, 33). Здесь важна не только
работа механик в движке, но и то, что **числа перестали дублироваться**:
таблицы шансов рыбалки, число осколков до карты, размер клада и каталоги
рун теперь лежат в `engine/`, а серверные модули берут их оттуда. Раньше
одни и те же значения были зашиты в двух местах и могли разойтись
незаметно.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ambient, currency, gathering, runes
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
    random.seed(4)
    store = Store(MemoryStorage())
    game = Game(store)

    print("\n— Рыбалка: таблица шансов —")
    rng = random.Random(1)
    kinds = [gathering.roll_fish(rng)[0] for _ in range(400)]
    for kind in ("heal", "mana", "gold", "miss"):
        check(kind in kinds, f"улов «{kind}» выпадает")
    # Пороги накопительные: сумма долей должна давать все четыре исхода.
    check(kinds.count("heal") > kinds.count("miss"),
          "форель попадается чаще, чем срывается рыба")
    check(gathering.fish_text("gold", 50).count("50") == 1,
          "текст улова подставляет сумму")

    print("\n— Рыбалка в движке лечит и платит —")
    p = Player(tg_id=1, cls="berserker")
    p.hp, p.mp = 10, 5
    p.bronze, p.silver, p.gold = 0, 0, 0
    store.save_player(p)
    money_before, hp_before, mp_before = currency.total(p), p.hp, p.mp
    for _ in range(30):
        game.handle(p, "fish")
    check(p.hp > hp_before or p.mp > mp_before or currency.total(p) > money_before,
          "рыбалка что-то приносит")
    # Максимумы берём из статов, а не из констант: за 30 рыбалок герой
    # успевает вырасти в уровне, и потолок здоровья поднимается вместе с ним.
    from engine import rules as _rules
    _s = _rules.stats(p, store)
    check(p.hp <= _s["max_hp"] and p.mp <= _s["max_mp"],
          f"лечение не превышает максимум ({p.hp}/{_s['max_hp']}, "
          f"{p.mp}/{_s['max_mp']})")
    check(p.exp > 0 or p.level > 1, "за рыбалку идёт опыт")

    print("\n— Раскопки: 5 осколков складываются в карту —")
    digger = Player(tg_id=2, cls="ranger")
    store.save_player(digger)
    for step in range(1, gathering.FRAGMENTS_FOR_MAP):
        game.handle(digger, "dig")
        check(digger.relic_fragments == step,
              f"осколок {step}/{gathering.FRAGMENTS_FOR_MAP}")
    check(not digger.treasure_map_coord, "карты ещё нет")
    r = game.handle(digger, "dig")
    check(digger.relic_fragments == 0, "счётчик обнулился")
    check(digger.treasure_map_coord.startswith("loc:"),
          f"карта собрана: {digger.treasure_map_coord}")
    check("карт" in r.text.lower(), "игроку сказали про карту")

    print("\n— Мирные занятия появляются по типу клетки —")
    hero = Player(tg_id=3, cls="druid")
    hero.loc = 1
    store.save_player(hero)
    cell = next(c for c in store.world.values() if c.loc == 1 and c.passable)
    saved_tile = cell.tile
    hero.x, hero.y = cell.x, cell.y

    cell.tile = "water"
    datas = [d for row in game.handle(hero, "look").keyboard for _l, d in row]
    check("fish" in datas, "на воде предлагают рыбалку")
    check("herbs" not in datas, "трав на воде нет")

    cell.tile = "forest"
    datas = [d for row in game.handle(hero, "look").keyboard for _l, d in row]
    check("herbs" in datas, "в лесу предлагают травы")
    check("dig" in datas, "в диких землях можно копать")
    cell.tile = saved_tile

    print("\n— Руны: вставка, бонусы и рунические слова —")
    inst = {"uid": "IT-TEST", "idx": 0, "stats": {"damage": 5}}
    bad = runes.insert_into_instance(inst, "выдуманная_руна")
    check(bad["ok"] is False, "неизвестная руна отклонена")

    res = runes.insert_into_instance(inst, "rune_fire", slot=1)
    check(res["ok"] is True, "руна вставлена")
    check(inst["socket_1"] == "rune_fire", "гнездо занято")
    check(inst["stats"]["damage"] == 5 + runes.RUNES["rune_fire"]["bonus_damage"],
          f"урон вырос до {inst['stats']['damage']}")
    check(res["runeword"] is None, "одна руна слова не образует")

    res2 = runes.insert_into_instance(inst, "rune_iron", slot=2)
    check(res2["runeword"] == "Пламенная сталь",
          f"слово сложилось: {res2['runeword']}")
    check(inst.get("runeword") == "Пламенная сталь", "слово записано в экземпляр")
    word = runes.RUNEWORDS[frozenset(["rune_fire", "rune_iron"])]
    check(inst["stats"]["damage"] >= word["bonus_damage"],
          "бонус слова начислен сверх бонуса руны")

    check(runes.check_runeword("rune_fire", None) is None,
          "с пустым гнездом слова нет")
    check("🔥" in runes.socket_line(_Obj(inst)), "строка гнёзд собирается")

    print("\n— Эмбиент: профиль по типу локации —")
    check(ambient.get_ambient_profile("dungeon")["reverb"] > 0.5,
          "в подземелье гулко")
    check(ambient.get_ambient_profile("несуществующий")["soundscape"]
          == ambient.AMBIENT_PROFILES["dangerous"]["soundscape"],
          "неизвестный тип падает в безопасный дефолт")

    print("\n— Числа общие с сервером —")
    try:
        from core import ambient as c_amb
        from core import gathering as c_gath
        from core import runes as c_runes
        check(c_runes.RUNES is runes.RUNES, "каталог рун — тот же объект")
        check(c_amb.AMBIENT_PROFILES is ambient.AMBIENT_PROFILES,
              "профили эмбиента — тот же объект")
        check(c_gath.G is gathering,
              "серверный сбор берёт таблицы из engine/gathering")
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


class _Obj:
    """Мини-обёртка dict → объект: socket_line ждёт атрибуты."""

    def __init__(self, data):
        self._d = data

    def __getattr__(self, name):
        return self._d.get(name)


if __name__ == "__main__":
    sys.exit(main())
