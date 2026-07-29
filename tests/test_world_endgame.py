"""Настройки VIP, достопримечательности, мировые боссы и объём контента.

python3 tests/test_world_endgame.py
"""
import os
import random
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import adminops, data, landmarks, stash
from engine import worldboss as WB
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
    p.loc, p.x, p.y = 0, 5, 5
    return p


# ── настройки кармана и VIP ─────────────────────────────────

def test_stash_tunables():
    print("\n— Карман и VIP настраиваются из панели —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    p.inventory = list(range(10))

    check(stash.capacity(p, store) == stash.SLOTS, "по умолчанию базовый размер")

    stash.set_tunables(store, {"stash_slots": 8, "stash_vip_bonus": 5})
    check(stash.capacity(p, store) == 8, "новый размер применился")
    stash.grant_vip(p, 10)
    check(stash.capacity(p, store) == 13, "прибавка VIP тоже из настроек")
    check("/13" in game.handle(p, "bag").text, "сумка показывает новый размер")
    check("/13" in game.handle(p, "stash").text, "экран кармана тоже")

    stash.revoke_vip(p)
    stash.set_tunables(store, {"stash_slots": 2})
    p.stash = []
    game.handle(p, "stput:0")
    game.handle(p, "stput:0")
    r = game.handle(p, "stput:0")
    check("полон" in (r.alert or ""), "новый лимит реально ограничивает")


def test_tunables_validation():
    print("\n— Границы и мусор в настройках —")
    store = fresh()

    stash.set_tunables(store, {"stash_loss_share": 5})
    check(stash.tune(store, "stash_loss_share") == 1.0, "доля больше 1 обрезается")
    stash.set_tunables(store, {"stash_loss_share": -3})
    check(stash.tune(store, "stash_loss_share") == 0.0, "отрицательная — в ноль")
    stash.set_tunables(store, {"stash_slots": "мусор"})
    check(isinstance(stash.tune(store, "stash_slots"), int), "мусор игнорируется")
    stash.set_tunables(store, {"stash_slots": ""})
    check(stash.tune(store, "stash_slots") == stash.SLOTS,
          "пустое поле возвращает значение по умолчанию")

    stash.set_tunables(store, {"vip_days": 90})
    check(stash.vip_days(store) == 90, "срок VIP берётся из настроек")


def test_loss_share_applies():
    print("\n— Доля потерь работает —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    p.equipped = {}

    stash.set_tunables(store, {"stash_loss_share": 1.0})
    p.inventory = [0, 1, 2, 3]
    lost = stash.drop_on_death(p, store=store)
    check(len(lost) == 4 and not p.inventory, "при 100% выпадает всё")

    stash.set_tunables(store, {"stash_loss_share": 0.0})
    p.inventory = [0, 1, 2, 3]
    lost = stash.drop_on_death(p, store=store)
    check(len(lost) == 1, "при 0% выпадает хотя бы одна вещь")


# ── достопримечательности ───────────────────────────────────

def test_landmarks_unique():
    print("\n— Диковины: по одной на локацию —")
    store = fresh()
    ks = landmarks.keys(store)
    check(ks, f"диковины расставлены: {len(ks)}")
    check(len(ks) < 60, f"их немного — {len(ks)}, а не сотни")
    check(landmarks.keys(store) == ks, "набор устойчив между вызовами")

    per = {}
    for key in ks:
        c = store.world[key]
        per.setdefault((c.loc, c.name), 0)
        per[(c.loc, c.name)] += 1
    check(all(v == 1 for v in per.values()),
          "в локации не больше одной диковины каждого вида")


def test_landmark_reward():
    print("\n— Награда за диковину —")
    random.seed(3)
    store = fresh()
    game = Game(store)
    p = hero(store, game)

    cell = store.world[sorted(landmarks.keys(store))[0]]
    p.loc, p.x, p.y = cell.loc, cell.x, cell.y
    from engine import mapview
    mapview.mark_visited(p)

    look = game.handle(p, "look")
    check(cell.name in look.text, "диковина видна при осмотре")
    check(any("study" in b[1] for row in look.keyboard for b in row),
          "есть кнопка «Изучить»")

    before = (p.gold, p.exp, p.strength, len(p.inventory), p.hp)
    r = game.handle(p, "study")
    after = (p.gold, p.exp, p.strength, len(p.inventory), p.hp)
    check(before != after, f"награда получена: {before} → {after}")
    check("Достопримечательностей" in r.text, "показан счётчик находок")
    check(bool(game.handle(p, "study").alert), "второй раз награду не дают")
    check(landmarks.total(store, p)[0] == 1, "находка засчитана")
    check("уже осмотрено" in game.handle(p, "look").text, "клетка помечена")


def test_landmark_kinds():
    print("\n— Все виды наград работают —")
    store = fresh()
    game = Game(store)
    kinds = {landmarks.of(store.world[k], store)["kind"]
             for k in landmarks.keys(store)}
    for i, kind in enumerate(sorted(kinds)):
        p = hero(store, game, 500 + i, f"Т{i}", "mage")
        cell = next(store.world[k] for k in landmarks.keys(store)
                    if landmarks.of(store.world[k], store)["kind"] == kind)
        p.loc, p.x, p.y = cell.loc, cell.x, cell.y
        p.hp = 1
        r = landmarks.claim(store, p, cell)
        check(not r.alert, f"награда «{kind}» выдана")


def test_landmark_duplicates_inert():
    print("\n— Копии диковин наградой не считаются —")
    store = fresh()
    real = store.world[sorted(landmarks.keys(store))[0]]
    dup = next((c for c in store.world.values()
                if c.name == real.name and c.loc == real.loc
                and c.key != real.key), None)
    if dup is None:
        check(True, "копий нет — проверять нечего")
        return
    check(landmarks.of(real, store) is not None, "настоящая диковина работает")
    check(landmarks.of(dup, store) is None, "копия не даёт награды")


# ── мировые боссы ───────────────────────────────────────────

def test_boss_summon_limits():
    print("\n— Призыв босса —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)

    check("тихо" in game.handle(p, "boss").text, "без босса в мире тихо")
    ev, info = adminops.boss_summon(store, None, "warden")
    check(ev["hp"] == WB.BOSSES["warden"]["hp"], f"призван: {info}")
    check(data.LOCATIONS[ev["loc"]][2] != "safe", "босс идёт в опасные земли")
    check(any("boss" in b[1] for row in game.handle(p, "menu").keyboard
              for b in row), "в меню появилась кнопка")

    try:
        adminops.boss_summon(store, None, "wyrm")
        check(False, "второго босса призвать нельзя")
    except adminops.Denied:
        check(True, "второго босса призвать нельзя")

    class Guest:
        tg_id, name = 5, "Гость"
        web_admin_role, web_admin_caps = "viewer", []

    try:
        adminops.boss_dismiss(store, Guest())
        check(False, "наблюдателю боссы недоступны")
    except adminops.Denied:
        check(True, "наблюдателю боссы недоступны")


def test_boss_shared_fight():
    print("\n— Общий бой и награда по вкладу —")
    random.seed(9)
    store = fresh()
    game = Game(store)
    a = hero(store, game, 1, "Гидеон")
    b = hero(store, game, 2, "Мара", "mage")
    for h in (a, b):
        h.level, h.max_hp, h.hp = 20, 5000, 5000
    a.strength, b.strength = 200, 100

    ev, _ = adminops.boss_summon(store, None, "warden")
    a.loc = b.loc = ev["loc"]

    a.loc = (ev["loc"] + 1) % len(data.LOCATIONS)
    check(bool(game.handle(a, "bosshit").alert), "издалека не ударить")
    a.loc = ev["loc"]
    a.level = 1
    check(bool(game.handle(a, "bosshit").alert), "низкий уровень не пускают")
    a.level = 20

    for _ in range(12):
        game.handle(a, "bosshit")
    for _ in range(4):
        game.handle(b, "bosshit")
    ev = WB.active(store)
    check(len(ev["damage"]) == 2, "оба вклада учтены")
    check(WB.contribution(ev, a) > WB.contribution(ev, b),
          f"вклад лидера выше: {WB.contribution(ev, a):.0%}")

    ev["hp"] = int(ev["max_hp"] * 0.51)
    game.handle(a, "bosshit")
    check(WB.active(store) and WB.active(store)["phase"] == 1,
          "на половине HP включилась вторая фаза")

    gold_a, gold_b = a.gold, b.gold
    WB.active(store)["hp"] = 1
    r = game.handle(a, "bosshit")
    check("последний удар" in r.text, "добивание объявлено")
    check(WB.active(store) is None, "босс ушёл из мира")
    check(a.gold > gold_a and b.gold > gold_b, "награду получили оба")
    check(a.gold - gold_a > b.gold - gold_b, "лидер получил больше")
    check(len(WB.history(store)) == 1, "бой попал в летопись")


def test_boss_expiry_and_dismiss():
    print("\n— Срок и роспуск —")
    store = fresh()
    ev, _ = adminops.boss_summon(store, None, "leviathan")
    ev["until"] = time.time() - 1
    check(WB.active(store) is None, "просроченный босс уходит сам")
    check(WB.history(store)[0]["won"] is False, "в летописи отмечен уход")

    adminops.boss_summon(store, None, "wyrm")
    adminops.boss_dismiss(store, None)
    check(WB.active(store) is None, "развеять можно вручную")


# ── объём контента ──────────────────────────────────────────

def test_content_volume():
    print("\n— Контента стало заметно больше —")
    check(len(data.MOBS) >= 20, f"мобов: {len(data.MOBS)}")
    check(len(data.ITEMS) >= 30, f"предметов: {len(data.ITEMS)}")
    check(len(data.NPCS) >= 10, f"жителей: {len(data.NPCS)}")

    locs = {m[8] for m in data.MOBS}
    check(locs >= set(range(len(data.LOCATIONS))),
          "в каждой локации есть свои твари")
    check(all(m[8] < len(data.LOCATIONS) for m in data.MOBS),
          "нет тварей с несуществующей локацией")

    kinds = {m[9] if len(m) > 9 else data.DEFAULT_BEHAVIOR for m in data.MOBS}
    check(kinds == set(data.BEHAVIORS), "представлены все характеры")

    types = {i[1] for i in data.ITEMS}
    check(types == {"weapon", "armor", "helmet", "boots", "accessory",
                    "consumable"}, "все слоты снаряжения заполнены")
    rarities = {i[2] for i in data.ITEMS}
    check("legendary" in rarities and "epic" in rarities,
          "есть высокая редкость, к которой можно стремиться")


def test_content_sanity():
    print("\n— Данные без опечаток —")
    names = ([m[0] for m in data.MOBS] + [i[0] for i in data.ITEMS]
             + [n[0] for n in data.NPCS])
    latin = [n for n in names if re.search(r"[A-Za-z]", n)]
    check(not latin, f"нет латиницы в русских названиях: {latin or 'ок'}")
    cjk = [n for n in names if re.search(r"[\u3000-\u9fff]", n)]
    check(not cjk, f"нет случайных иероглифов: {cjk or 'ок'}")
    check(len(names) == len(set(names)), "имена не повторяются")

    for i in data.ITEMS:
        if i[3] <= 0:
            check(False, f"нулевая цена у «{i[0]}»")
            break
    else:
        check(True, "у всех предметов положительная цена")

    npc_types = {n[2] for n in data.NPCS}
    check(npc_types <= {"merchant", "healer", "storyteller", "smith"},
          f"типы жителей известны: {npc_types}")


def test_new_npc_types_work():
    print("\n— Новые жители отвечают —")
    store = fresh()
    game = Game(store)
    p = hero(store, game)
    for idx, n in enumerate(data.NPCS):
        try:
            r = game.handle(p, f"talk:{idx}")
            ok = bool(r.text) and n[0] in r.text
            if n[2] == "smith":
                ok = ok and any("craft" in b[1] for row in r.keyboard for b in row)
            check(ok, f"«{n[0]}» ({n[2]}) отвечает")
        except Exception as e:
            check(False, f"«{n[0]}» → {type(e).__name__}: {e}")


def test_panel_renders():
    print("\n— Панель с новыми блоками —")
    from webapp.pages import content as page_content
    from webapp.pages import world as page_world

    store = fresh()
    game = Game(store)
    p = hero(store, game)
    stash.grant_vip(p, 30)
    adminops.boss_summon(store, None, "warden")

    class Ctx:
        pass

    ctx = Ctx()
    ctx.store = store
    ctx.state = {"loc": 0, "world_tab": "living", "cell_pick": ""}
    try:
        markup = page_world.render(ctx)
        check("Инвентарь, потери и VIP" in markup, "блок настроек VIP на месте")
        check("stash-save" in markup, "есть кнопка сохранения")
        check("VIP-игроки" in markup, "виден список VIP")
    except Exception as e:
        check(False, f"вкладка «Жизнь мира» → {type(e).__name__}: {e}")

    ctx.state["world_tab"] = "cataclysms"
    try:
        markup = page_world.render(ctx)
        check("Мировой босс" in markup, "блок босса нарисован")
        check("boss-summon" in markup, "есть кнопки призыва")
    except Exception as e:
        check(False, f"вкладка «Катаклизмы» → {type(e).__name__}: {e}")

    try:
        check(len(page_content.render(ctx)) > 500, "страница контента цела")
    except Exception as e:
        check(False, f"контент → {type(e).__name__}: {e}")


def main():
    for fn in (test_stash_tunables, test_tunables_validation,
               test_loss_share_applies,
               test_landmarks_unique, test_landmark_reward,
               test_landmark_kinds, test_landmark_duplicates_inert,
               test_boss_summon_limits, test_boss_shared_fight,
               test_boss_expiry_and_dismiss,
               test_content_volume, test_content_sanity,
               test_new_npc_types_work, test_panel_renders):
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
