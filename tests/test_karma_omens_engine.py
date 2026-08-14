"""Карма, знамения и именные экземпляры: регрессии этой серии.

Запуск: python3 tests/test_karma_omens_engine.py

Покрывает:
  • карму браузерного стека (кламп, пороги, поступки, эффекты);
  • карму в бою (нежить даёт +KILL_UNDEAD, зверьё — ничего);
  • знамения (один каталог на оба стека);
  • именные экземпляры в бою (player.worn → статы экземпляра, а не шаблона);
  • могилы с этажом (погиб в подземелье — могила не светится наверху);
  • карму за разграбление чужой могилы;
  • кнопку «Знамения» и строку кармы в меню/профиле движка.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import combat, data, death, inventory, items, karma, omens, rules
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
    random.seed(7)

    print("\n— Карма: кламп, пороги, поступки —")
    p = Player(tg_id=1, cls="berserker")
    check(karma.change_karma(p, 999) == karma.MAX_KARMA,
          f"кламп сверху: {p.karma_score} = {karma.MAX_KARMA}")
    p.karma_score = 0
    check(karma.change_karma(p, -999) == karma.MIN_KARMA,
          f"кламп снизу: {p.karma_score} = {karma.MIN_KARMA}")
    p.karma_score = 100
    check(karma.karma_status(p)[0] == "⚖️", "100 очков — нейтральный")
    check(karma.pious(p) is False and karma.defiled(p) is False,
          "100 очков: эффекты порогов не активны")
    p.karma_score = karma.PIOUS_KARMA
    check(karma.karma_status(p)[0] == "✨" and karma.pious(p),
          f"+{karma.PIOUS_KARMA}: Благочестивый")
    p.karma_score = karma.DEFILED_KARMA
    check(karma.karma_status(p)[0] == "💀" and karma.defiled(p),
          f"{karma.DEFILED_KARMA}: Осквернитель")
    check(karma.is_undead("Болотный зомби") and karma.is_undead("Костяной жрец"),
          "нежить узнаётся по имени")
    check(not karma.is_undead("Лесной ворг"), "ворг — не нежить")

    p.karma_score = 0
    line = karma.on_kill(p, "Болотный зомби")
    check(p.karma_score == karma.KILL_UNDEAD and "нежити" in line,
          f"нежить даёт +{karma.KILL_UNDEAD}")
    line2 = karma.on_kill(p, "Лесной ворг")
    check(p.karma_score == karma.KILL_UNDEAD and line2 == "",
          "зверьё карму не трогает")
    karma.on_grave_loot(p)
    check(p.karma_score == karma.KILL_UNDEAD + karma.GRAVE_LOOT,
          f"чужая могила даёт {karma.GRAVE_LOOT}")
    p.karma_score = 0
    karma.on_boss(p)
    check(p.karma_score == karma.KILL_BOSS, f"босс даёт +{karma.KILL_BOSS}")

    print("\n— Карма в бою —")
    store = Store(MemoryStorage())
    p2 = Player(tg_id=2, cls="berserker")
    p2.loc, p2.x, p2.y = 1, 3, 3
    store.save_player(p2)
    combat.start(p2, 1, store=store)          # Болотный зомби — нежить
    guard = 0
    while p2.combat and guard < 200:
        combat.action(p2, "hit", store.world, store)
        guard += 1
    check(not p2.combat, "бой доведён до конца")
    check(p2.karma_score == karma.KILL_UNDEAD,
          f"карма за бой с нежитью: {p2.karma_score}")

    print("\n— Знамения: один каталог на оба стека —")
    from core import omens as core_omens
    check(core_omens.get_current_omens() == omens.get_current_omens(),
          "core/omens.py отдаёт каталог engine/omens.py")
    check(len(omens.get_current_omens()) == 3, "в каталоге три знамения")
    check("Кровавый туман" in omens.omens_text(), "текст экрана собирается")

    print("\n— Именные экземпляры в бою (player.worn) —")
    p3 = Player(tg_id=3, cls="berserker")
    store.save_player(p3)
    weapon_idx = next(i for i, t in enumerate(data.ITEMS) if t[1] == "weapon")
    inst = items.create(store, weapon_idx, source="mob", owner=p3.tg_id, luck=0)
    inst["stats"] = {"damage": 37}            # известные статы экземпляра
    p3.inventory.append(weapon_idx)
    inventory.equip(p3, 0, store)
    check(p3.equipped.get("weapon") == weapon_idx
          and p3.worn.get("weapon") == inst["uid"],
          "надевание пишет uid экземпляра в player.worn")
    s = rules.stats(p3, store)
    check(s["damage"] == 37, f"в бою статы экземпляра: {s['damage']} = 37")
    inventory.unequip(p3, 0, store)
    check(p3.worn.get("weapon") is None, "снятие чистит player.worn")
    check(rules.stats(p3, store)["damage"] == 0,
          "после снятия статов экземпляра нет")
    s0 = rules.stats(p3)                      # без store — как раньше, шаблон
    check(s0["damage"] == 0, "без store бонусы не выдумываются")

    print("\n— Могила помнит этаж —")
    p4 = Player(tg_id=4, cls="berserker")
    p4.loc, p4.x, p4.y, p4.floor = 3, 3, 3, 1
    store2 = Store(MemoryStorage())
    grave = death.bury(store2, p4, 50)
    check(grave["floor"] == 1, "надгробие хранит этаж гибели")
    check(death.at(store2, 3, 3, 3, 0) is None,
          "на поверхности могилы из подземелья нет")
    check(death.at(store2, 3, 3, 3, 1) is not None,
          "на своём этаже могила находится")
    check("3:1:3:3" in death.keys(store2), "ключ карты учитывает этаж")

    p5 = Player(tg_id=5, cls="berserker")
    p5.loc, p5.x, p5.y, p5.floor = 3, 3, 3, 1
    store2.save_player(p5)
    reply = death.claim(store2, p5)           # чужое надгробие
    check(p5.karma_score == karma.GRAVE_LOOT,
          f"мародёрство: карма {p5.karma_score} = {karma.GRAVE_LOOT}")
    check("💀" in reply.text, "экран могилы показывает падение кармы")

    print("\n— Меню и профиль движка —")
    game = Game(store)
    m = game.menu(p3)
    datas = [d for row in m.keyboard for _l, d in row]
    check("omens" in datas, "в меню есть кнопка «Знамения»")
    check("🔮" in game.do_omens(p3).text, "экран знамений открывается")
    from engine import texts
    check("Карма" in texts.profile(p3, store), "профиль показывает карму")
    check(hasattr(Player(tg_id=9), "bronze"), "у Player есть поле bronze")
    from engine.currency import currency_str
    check(currency_str(Player(tg_id=9)) == "0🟤 0⚪ 50🟡",
          "профиль показывает три валюты")

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
