"""Характеры тварей, цена смерти и отряды.

python3 tests/test_social_world.py
"""
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import behavior, combat, data, death, party, rules
from engine import world as W
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


def hero(store, game, tg_id=1, name="Герой", cls="warrior"):
    p = store.player(tg_id, name)
    game.handle(p, f"make:{cls}")
    p.max_hp = p.hp = 99999
    p.strength = 900
    return p


# ── 3. Характеры тварей ─────────────────────────────────────

def test_behaviors_declared():
    print("\n— Характеры объявлены —")
    check(behavior.of(0) == "passive", "зомби пассивен")
    check(behavior.of(1) == "hunter", "ворг охотник")
    check(behavior.of(2) == "territorial", "скелет территориален")
    check("Охотник" in behavior.label(1), f"подпись читаема: {behavior.label(1)}")

    # У старых записей поля нет — не должно падать.
    saved = list(data.MOBS)
    try:
        data.MOBS.append(("Древний", "без характера", 1, 10, 1, 1, 1, 1, 0))
        check(behavior.of(len(data.MOBS) - 1) == data.DEFAULT_BEHAVIOR,
              "моб без поля читается как пассивный")
    finally:
        data.MOBS[:] = saved


def _ambush_rate(store, p, dist, mob_index, tries=300):
    hits = 0
    for _ in range(tries):
        for c in store.world.values():
            if c.loc == 1:
                c.mob = -1
        p.loc, p.x, p.y, p.combat = 1, 5, 5, {}
        target = W.cell_at(store.world, 1, 5 + dist, 5)
        target.mob, target.passable = mob_index, True
        if behavior.hunters_near(store, p) is not None:
            hits += 1
    return hits


def test_aggression_by_character():
    print("\n— Кто нападает сам —")
    random.seed(5)
    store = fresh()
    game = Game(store)
    p = hero(store, game)

    check(_ambush_rate(store, p, 1, 0) == 0, "пассивный не нападает никогда")
    check(_ambush_rate(store, p, 2, 2) == 0, "территориальный издалека не достаёт")

    close = _ambush_rate(store, p, 1, 2)
    check(50 < close < 160, f"территориальный вплотную бросается: {close}/300")

    near = _ambush_rate(store, p, 1, 1)
    far = _ambush_rate(store, p, 2, 1)
    check(near > 80, f"охотник вплотную нападает часто: {near}/300")
    check(0 < far < near, f"издалека решается реже: {far}/300 против {near}/300")


def test_wandering():
    print("\n— Бродяжничество —")
    random.seed(7)
    store = fresh()

    for c in store.world.values():
        if c.loc == 1:
            c.mob = -1
    spot = next(c for c in store.world.values()
                if c.loc == 1 and c.passable and (c.x, c.y) != W.SPAWN)
    spot.mob = 1                                     # ворг
    moved = sum(behavior.wander(store, 1) for _ in range(40))
    alive = [c for c in store.world.values() if c.loc == 1 and c.mob >= 0]
    check(moved > 0, f"охотник сдвинулся {moved} раз")
    check(len(alive) == 1, "тварь не размножилась и не пропала")

    for c in store.world.values():
        if c.loc == 1:
            c.mob = -1
    spot = next(c for c in store.world.values()
                if c.loc == 1 and c.passable and (c.x, c.y) != W.SPAWN)
    spot.mob = 0                                     # зомби
    check(sum(behavior.wander(store, 1) for _ in range(40)) == 0,
          "пассивный остаётся на месте")

    store.settings[behavior.WANDER_SETTING] = False
    spot.mob = 1
    check(sum(behavior.wander(store, 1) for _ in range(20)) == 0,
          "выключатель брожения работает")


# ── 6. Цена смерти ──────────────────────────────────────────

def test_death_grave():
    print("\n— Смерть оставляет надгробие —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    # Слабый герой против Пожирателя: гибель гарантирована.
    p.gold, p.hp, p.max_hp, p.strength = 500, 1, 100, 1
    p.loc, p.x, p.y = 1, 3, 3

    r = combat.start(p, 6, store=store)              # Пожиратель добьёт
    for _ in range(10):
        if not p.combat:
            break
        r = combat.action(p, "hit", store.world, store)
    check("Поражение" in r.text, "экран поражения показан")
    check(p.gold == 400, f"потеряно 20%: осталось {p.gold}")
    check((p.loc, p.x, p.y) == (0, W.SPAWN[0], W.SPAWN[1]), "возврат на спавн")

    g = death.mine(store, p)
    check(g is not None, "надгробие записано")
    check((g["loc"], g["x"], g["y"]) == (1, 3, 3), "лежит на месте гибели")
    check(g["gold"] == 100, "в нём всё потерянное золото")

    check(bool(game.handle(p, "claim").alert), "издалека не забрать")
    p.loc, p.x, p.y = g["loc"], g["x"], g["y"]
    before = p.gold
    r = game.handle(p, "claim")
    check(p.gold - before == 100, "на месте вернул всё до монеты")
    check(death.mine(store, p) is None, "могила исчезла после возврата")


def test_death_wounds():
    print("\n— Раны после смерти —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    p.strength = 20

    healthy = rules.stats(p)["strength"]
    death.wound(p)
    check(death.wounded(p), "герой ранен")
    hurt = rules.stats(p)["strength"]
    check(hurt < healthy, f"статы просели: {healthy} → {hurt}")
    check(rules.stats(p)["max_hp"] >= p.hp, "максимум HP не порезан")
    check("Раны" in death.note(p), "игрок предупреждён о ранах")

    r = game.handle(p, "heal")
    check("Раны затянулись" in r.text, "лекарь лечит раны")
    check(not death.wounded(p), "после лекаря здоров")
    check(rules.stats(p)["strength"] == healthy, "статы вернулись")


def test_grave_looting_and_decay():
    print("\n— Чужие могилы и истлевание —")
    store = fresh()
    game = Game(store)
    a = hero(store, game, 1, "Гидеон")
    b = hero(store, game, 2, "Мара", "mage")

    b.loc, b.x, b.y = 1, 7, 7
    death.bury(store, b, 100)
    a.loc, a.x, a.y = 1, 7, 7
    before = a.gold
    r = game.handle(a, "claim")
    check(a.gold - before == 50, "с чужой могилы берётся половина")
    check("прах" in r.text, "объяснено, почему половина")

    death.bury(store, a, 80)
    g = death.mine(store, a)
    g["at"] = time.time() - (death.GRAVE_HOURS + 1) * 3600
    check(death.decay(store) == 1, "старая могила истлела")
    check(death.mine(store, a) is None, "и пропала из мира")

    # Одна могила на героя: новая смерть заменяет прежнюю.
    death.bury(store, a, 10)
    death.bury(store, a, 20)
    check(len([x for x in store.settings[death.GRAVES]
               if x["owner"] == a.tg_id]) == 1, "у героя только одна могила")


# ── 5. Отряды ───────────────────────────────────────────────

def test_party_assembly():
    print("\n— Сбор отряда —")
    store = fresh()
    game = Game(store)
    a = hero(store, game, 1, "Гидеон")
    b = hero(store, game, 2, "Мара", "mage")
    c = hero(store, game, 3, "Тень", "rogue")
    d = hero(store, game, 4, "Лишний", "cleric")

    check("одиночку" in game.handle(a, "party").text, "сначала герой один")
    game.handle(a, "invite:Мара")
    check(b.party_invite != 0, "приглашение доставлено")
    check("зовёт" in game.handle(b, "party").text, "приглашённый видит зов")

    game.handle(b, "pjoin")
    check(len(party.of(store, a)["members"]) == 2, "в отряде двое")
    check(party.is_leader(store, a), "предводитель — тот, кто позвал")

    check(bool(game.handle(b, "invite:Тень").alert), "рядовой не зовёт")
    game.handle(a, "invite:Тень")
    game.handle(c, "pjoin")
    r = game.handle(a, "invite:Лишний")
    check(bool(r.alert), f"больше {party.MAX_SIZE} не собрать")
    check(bool(game.handle(a, "invite:Мара").alert), "занятого не позвать")
    check(bool(game.handle(a, "invite:Гидеон").alert), "себя не позвать")
    check(bool(game.handle(a, "invite:Нетакого").alert), "выдуманного не позвать")


def test_party_share():
    print("\n— Общая добыча —")
    store = fresh()
    game = Game(store)
    a = hero(store, game, 1, "Гидеон")
    b = hero(store, game, 2, "Мара", "mage")
    c = hero(store, game, 3, "Тень", "rogue")
    game.handle(a, "invite:Мара")
    game.handle(b, "pjoin")
    game.handle(a, "invite:Тень")
    game.handle(c, "pjoin")

    cell = next(x for x in store.world.values() if x.loc == 1 and x.mob >= 0)
    a.loc, a.x, a.y = 1, cell.x, cell.y
    b.loc, b.x, b.y = 1, cell.x, cell.y
    c.loc = 2                                        # третий далеко
    gold_b, gold_c = b.gold, c.gold

    combat.start(a, cell.mob, store=store)
    for _ in range(30):
        if not a.combat:
            break
        r = combat.action(a, "hit", store.world, store)
    check(b.gold > gold_b, f"соратник рядом получил долю: +{b.gold - gold_b}")
    check(c.gold == gold_c, "тот, кто в другой локации, не получил ничего")
    check("Мара" in r.text, "делёж виден в отчёте боя")


def test_party_balance():
    print("\n— Баланс дележа —")
    check(party._fund(1) == 1.0, "одиночке — обычная награда, без бонуса")
    check(party._fund(2) > party._fund(1), "вдвоём отряд получает больше")
    check(party._fund(3) > party._fund(2), "втроём — ещё больше")
    check(party._fund(3) <= party.MAX_TOTAL, "фонд ограничен сверху")
    check(party._fund(2) / 2 < 1.0, "но доля каждого меньше сольной")

    store = fresh()
    game = Game(store)
    a = hero(store, game, 1, "Один")
    check(party.bonus(store, a) == 1.0, "без отряда множитель нейтрален")
    b = hero(store, game, 2, "Два", "mage")
    game.handle(a, "invite:Два")
    game.handle(b, "pjoin")
    b.loc = 5                                        # соратник далеко
    check(party.bonus(store, a) == 1.0,
          "отряд без соратников рядом бонуса не даёт")


def test_party_leaving():
    print("\n— Роспуск —")
    store = fresh()
    game = Game(store)
    a = hero(store, game, 1, "Гидеон")
    b = hero(store, game, 2, "Мара", "mage")
    c = hero(store, game, 3, "Тень", "rogue")
    game.handle(a, "invite:Мара")
    game.handle(b, "pjoin")
    game.handle(a, "invite:Тень")
    game.handle(c, "pjoin")

    game.handle(a, "pleave")                         # ушёл предводитель
    check(party.of(store, b) is not None, "отряд уцелел")
    check(party.is_leader(store, b) or party.is_leader(store, c),
          "предводительство передано")
    game.handle(b, "pleave")
    check(party.of(store, c) is None, "отряд из одного распался")
    check(bool(game.handle(c, "pleave").alert), "выйти дважды нельзя")


def test_party_invite_decline():
    print("\n— Отказ от приглашения —")
    store = fresh()
    game = Game(store)
    a = hero(store, game, 1, "Гидеон")
    b = hero(store, game, 2, "Мара", "mage")
    game.handle(a, "invite:Мара")
    game.handle(b, "pno")
    check(b.party_invite == 0, "приглашение снято")
    check(party.of(store, b) is None, "в отряд не попал")
    check(bool(game.handle(b, "pjoin").alert), "принять после отказа нельзя")


def test_panel_with_data():
    """Вкладка «Жизнь мира» с непустыми данными.

    Пустая страница рендерится всегда — падало только при живых надгробиях
    и отрядах, поэтому проверяем именно наполненный случай.
    """
    print("\n— Панель: жизнь мира —")
    from webapp.pages import content as page_content
    from webapp.pages import world as page_world

    store = fresh()
    game = Game(store)
    a = hero(store, game, 1, "Гидеон")
    b = hero(store, game, 2, "Мара", "mage")
    game.handle(a, "invite:Мара")
    game.handle(b, "pjoin")
    death.bury(store, a, 150)

    class Ctx:
        pass

    ctx = Ctx()
    ctx.store = store
    ctx.state = {"loc": 0, "world_tab": "living", "cell_pick": ""}

    try:
        markup = page_world.render(ctx)
        check("Характеры тварей" in markup, "блок характеров нарисован")
        check("Гидеон" in markup and "Надгробия" in markup, "надгробие видно")
        check("Отряды (1)" in markup, "отряд виден")
        check("behavior-save" in markup, "выключатели поведения на месте")
    except Exception as e:
        check(False, f"вкладка «Жизнь мира» → {type(e).__name__}: {e}")

    for tab in ("map", "grid", "cataclysms", "living", "dungeons"):
        ctx.state["world_tab"] = tab
        try:
            page_world.render(ctx)
            check(True, f"вкладка {tab} рисуется")
        except Exception as e:
            check(False, f"вкладка {tab} → {type(e).__name__}: {e}")

    check("mf_behavior" in page_content.mob_form(ctx, 0),
          "в редакторе моба есть выбор характера")
    check("Нрав" in page_content.render(ctx), "нрав виден в списке мобов")


def main():
    for fn in (test_behaviors_declared, test_aggression_by_character,
               test_wandering,
               test_death_grave, test_death_wounds,
               test_grave_looting_and_decay,
               test_party_assembly, test_party_share, test_party_balance,
               test_party_leaving, test_party_invite_decline,
               test_panel_with_data):
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
