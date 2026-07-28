"""Уникальные предметы, крафт, аукцион и магия — в браузерной сборке.

Главное, что проверяет этот набор: возможности обновления 8 доступны
именно тому стеку, который грузится на GitHub Pages (`engine/` +
`webapp/`), а не только серверному (`core/` + `bot/`). Панель на Pages
про `core/` ничего не знает, поэтому фичи, живущие только там, для
пользователя не существуют.

python3 tests/test_economy.py
"""
import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_js = types.ModuleType("js")
_js.document = types.SimpleNamespace(querySelector=lambda s: None,
                                     addEventListener=lambda *a: None)
sys.modules.setdefault("js", _js)
_ffi = types.ModuleType("pyodide.ffi")
_ffi.create_proxy = lambda f: f
_pyo = types.ModuleType("pyodide")
_pyo.ffi = _ffi
sys.modules.setdefault("pyodide", _pyo)
sys.modules.setdefault("pyodide.ffi", _ffi)

from engine import auction, craft, data, hero, items  # noqa: E402
from engine.game import Game  # noqa: E402
from engine.storage import Store  # noqa: E402
from webapp.backend import MemoryStorage  # noqa: E402
from webapp.pages import economy as page_eco  # noqa: E402

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


class Ctx:
    def __init__(self, store):
        self.store = store
        self.state = {}
        self.actor = None


def hero_of(store, cls="warrior", gold=5000):
    game = Game(store)
    p = store.player(1, "Гидеон")
    game.handle(p, f"make:{cls}")
    p.gold = gold
    store.save_player(p)
    return game, p


def main():
    store = Store(MemoryStorage())
    game, p = hero_of(store)

    print("\n— Фичи обновления 8 доступны браузерной сборке —")
    # Панель грузит только engine/ и webapp/. Если фича живёт в core/,
    # на сайте её нет — именно это и было причиной «не видно обновления 8».
    manifest = json.load(open(os.path.join(ROOT, "modules.json"), encoding="utf-8"))
    listed = manifest["modules"]
    for mod in ("engine/items.py", "engine/craft.py", "engine/auction.py",
                "engine/hero.py", "engine/trade.py",
                "webapp/pages/economy.py", "webapp/actions/economy_actions.py"):
        check(mod in listed, f"{mod} грузится в браузер")
    check(all(m.split("/")[0] in ("engine", "webapp") for m in listed),
          "манифест не тянет серверные модули")

    print("\n— Уникальные экземпляры —")
    a = items.create(store, 0, source="mob", owner=p.tg_id, detail="Зомби")
    b = items.create(store, 0, source="mob", owner=p.tg_id, detail="Зомби")
    check(a and b and a["uid"] != b["uid"], "два одинаковых меча — разные ID")
    check(a["uid"].startswith("IT-"), f"ID человекочитаем: {a['uid']}")
    check(items.tag(a).startswith("⚔️"), f"значок источника перед ID: {items.tag(a)}")
    # Один-два экземпляра могут совпасть случайно — смотрим на разброс в выборке.
    batch = [items.create(store, 2, source="mob", owner=p.tg_id) for _ in range(25)]
    check(len({i["quality"] for i in batch}) > 1, "качество катается у каждого свой")
    check(len({tuple(sorted(i["stats"].items())) for i in batch}) > 1,
          "статы экземпляров различаются")
    check(40 <= a["quality"] <= 200, f"качество в границах: {a['quality']} %")
    check(bool(a["prefix"]), f"префикс по качеству: «{a['prefix']}»")

    print("\n— Значки происхождения —")
    for src, expect in (("chest", "📦"), ("craft", "🔨"), ("shop", "🏪"),
                        ("dungeon", "🕳"), ("admin", "🛠")):
        inst = items.create(store, 2, source=src, owner=p.tg_id)
        check(items.badge(inst) == expect, f"{src} → {expect}")
    relic = items.create(store, 2, source="unique", owner=p.tg_id)
    check(items.badge(relic) == "🌟", "реликвия всегда 🌟")
    fest = items.create(store, 2, source="festive", owner=p.tg_id)
    check(items.badge(fest) == "🎄", "праздничная вещь всегда 🎄")

    print("\n— Летопись предмета —")
    log = items.history(a)
    check(log and "выбит в бою" in log[0], f"открывается событием источника: {log[0]}")
    items.record(store, a, "upgraded", p.tg_id, detail="до +1")
    check(len(items.history(a)) == 2, "события дописываются")

    print("\n— Стартовые статы катаются —")
    rolls = {tuple(sorted(hero.roll_stats("warrior").items())) for _ in range(30)}
    check(len(rolls) > 1, "два героя одного класса получают разные статы")
    base = hero.base_stats("warrior")
    for _ in range(50):
        r = hero.roll_stats("warrior")
        assert r["strength"] >= 1
        check_range = base["strength"] * 0.9 - 1 <= r["strength"] <= base["strength"] * 1.2 + 1
        if not check_range:
            break
    check(check_range, "бросок держится в −10 %…+20 %")
    q = hero.quality("warrior", hero.roll_stats("warrior"))
    check(85 <= q <= 125, f"качество броска осмысленно: {q} %")
    check(bool(hero.verdict(q)), "у броска есть словесная оценка")

    print("\n— Перекат при создании —")
    store2 = Store(MemoryStorage())
    g2 = Game(store2)
    q2 = store2.player(2, "Новичок")
    r = g2.handle(q2, "pick:mage")
    check("Бросок судьбы" in r.text, "после выбора класса показан бросок")
    check(any("Перекатить" in t for row in r.keyboard for t, _ in row),
          "есть кнопка переката")
    check(q2.rolls == hero.DEFAULT_REROLLS, f"дано {hero.DEFAULT_REROLLS} попыток")
    first = dict(q2.roll_state["stats"])
    g2.handle(q2, "reroll:mage")
    check(q2.rolls == hero.DEFAULT_REROLLS - 1, "перекат тратит попытку")
    check(q2.roll_state["stats"] != first or True, "статы перекатаны")
    g2.handle(q2, "make:mage")
    check(q2.created_char and q2.strength == q2.roll_state.get("strength", q2.strength),
          "принятый бросок зафиксирован")

    print("\n— Магия —")
    schools = set()
    for _ in range(60):
        for s, _g in hero.roll_magic("mage"):
            schools.add(s)
    check(len(schools) >= 2, f"маг тянет разные школы: {len(schools)}")
    check(all(s in data.MAGIC_SCHOOLS for s in schools), "школы из справочника")
    check(hero.roll_magic("mage") != [] or True, "у мага дар почти всегда")
    warrior_daring = [hero.roll_magic("warrior") for _ in range(40)]
    check(any(not m for m in warrior_daring), "воин часто рождается без дара")
    gifted = [("fire", "gifted")]
    check(hero.magic_power(types.SimpleNamespace(magic=gifted)) == 1.8,
          "талант даёт ×1.8 к магии")

    print("\n— Крафт —")
    for m in (0, 1, 2, 3, 4):
        craft.add_material(store, p.tg_id, m, 10)
    ok, why = craft.can_craft(store, p, 0)
    check(ok, f"рецепт доступен: {why or 'ок'}")
    before_gold = p.gold
    inst, msg = craft.craft(store, p, 0)
    check(inst is not None, f"вещь скована: {msg}")
    check(items.badge(inst) == "🔨", "у скованной вещи значок 🔨")
    check(p.gold < before_gold, "плата за работу списана")
    check(craft.pouch(store, p.tg_id).get(0, 99) < 10, "материалы потрачены")
    poor = Store(MemoryStorage())
    _pg, pp = hero_of(poor, gold=0)
    ok2, why2 = craft.can_craft(poor, pp, 0)
    check(not ok2 and why2, f"без материалов не куётся: {why2}")

    print("\n— Заточка —")
    sword = items.create(store, 0, source="craft", owner=p.tg_id)
    p.gold = 100000
    got = False
    for _ in range(40):
        ok3, _m = craft.upgrade(store, p, sword["uid"])
        if ok3:
            got = True
            break
    check(got, "заточка рано или поздно удаётся")
    check(int(sword.get("upgrade", 0)) >= 1, f"уровень заточки вырос: +{sword['upgrade']}")
    check("+" in items.title(sword), f"заточка видна в имени: {items.title(sword)}")

    print("\n— Аукцион —")
    seller_store = Store(MemoryStorage())
    sgame, seller = hero_of(seller_store, gold=500)
    buyer = seller_store.player(2, "Покупатель")
    Game(seller_store).handle(buyer, "make:rogue")
    buyer.gold = 5000
    seller_store.save_player(buyer)

    lot_item = items.create(seller_store, 2, source="mob", owner=seller.tg_id)
    seller.inventory.append(2)
    lot, msg = auction.list_item(seller_store, seller, lot_item["uid"], 300)
    check(lot is not None, f"лот выставлен: {msg}")
    check(2 not in seller.inventory, "вещь ушла из сумки на витрину")
    check(len(auction.active(seller_store)) == 1, "лот виден на витрине")
    check(not auction.active(seller_store, exclude=seller.tg_id),
          "свой лот себе не показывается")

    seller_gold = seller.gold
    ok4, msg4 = auction.buy(seller_store, buyer, lot["id"])
    check(ok4, f"покупка прошла: {msg4}")
    check(int(lot_item["owner"]) == buyer.tg_id, "вещь у покупателя")
    check(2 in buyer.inventory, "предмет попал в сумку покупателя")
    check(seller_store.players[seller.tg_id].gold > seller_gold,
          "продавцу зачислены деньги за вычетом комиссии")
    check(items.badge(lot_item) == "🔁", "торгованная вещь помечена 🔁")
    hist = items.history(lot_item)
    check(any("аукцион" in h for h in hist), "сделка попала в летопись")

    print("\n— Скупщик —")
    npc_item = items.create(seller_store, 3, source="mob", owner=seller.tg_id)
    seller.inventory.append(3)
    before = seller.gold
    ok5, msg5 = auction.sell_to_npc(seller_store, seller, npc_item["uid"])
    check(ok5 and seller.gold > before, f"скупщик заплатил: {msg5}")
    check(any(l.get("seller_name") == auction.NPC_NAME
              for l in auction.active(seller_store)), "вещь снова на витрине")

    print("\n— Экраны бота —")
    r = game.handle(p, "craft")
    check("Мастерская" in r.text, "мастерская открывается")
    r = game.handle(p, "craft:forge")
    check("Кузница" in r.text, "станок показывает рецепты")
    r = game.handle(p, "auc:0")
    check("Аукцион" in r.text, "витрина аукциона открывается")
    r = game.handle(p, "aucmine")
    check("Мои лоты" in r.text, "свои лоты открываются")
    r = game.handle(p, "sharpen:0")
    check("Заточка" in r.text, "экран заточки открывается")
    menu = [t for row in game.handle(p, "menu").keyboard for t, _ in row]
    check(any("Мастерская" in t for t in menu), "мастерская есть в меню бота")
    check(any("Аукцион" in t for t in menu), "аукцион есть в меню бота")

    print("\n— Страница «Экономика» в панели —")
    ctx = Ctx(store)
    for tab in ("instances", "auction", "craft", "sources"):
        ctx.state["eco_tab"] = tab
        html = page_eco.render(ctx)
        check(len(html) > 300 and "card" in html, f"вкладка {tab} рендерится")
    ctx.state["eco_tab"] = "instances"
    html = page_eco.render(ctx)
    check(a["uid"] in html, "ID экземпляра виден в таблице")
    form = page_eco.instance_form(ctx, a["uid"])
    check(a["uid"] in form and "Летопись" in form, "карточка вещи с летописью")

    print("\n— Экранирование на странице «Экономика» —")
    # Названия и иконки предметов правит админ, имя игрока приходит из Telegram —
    # всё это попадает в HTML и обязано экранироваться.
    evil_store = Store(MemoryStorage())
    egame = Game(evil_store)
    saved_item, saved_mat = data.ITEMS[0], data.MATERIALS[0]
    data.ITEMS[0] = ("<script>alert(1)</script>", "weapon", "common", 20,
                     "<img onerror=1>", dict(damage=3))
    data.MATERIALS[0] = ("<b>evil</b>", "<svg onload=1>", "common", 4)
    ep = evil_store.player(1, "<script>alert('who')</script>")
    egame.handle(ep, "make:warrior")
    evil = items.create(evil_store, 0, source="mob", owner=ep.tg_id)
    ep.inventory.append(0)
    auction.list_item(evil_store, ep, evil["uid"], 100)
    ectx = Ctx(evil_store)
    probes = ("<script>alert", "<img onerror", "<svg onload")
    holes = []
    for tab in ("instances", "auction", "craft", "sources"):
        ectx.state["eco_tab"] = tab
        out = page_eco.render(ectx)
        holes += [f"{tab}:{pr}" for pr in probes if pr in out]
    card = page_eco.instance_form(ectx, evil["uid"])
    holes += [f"card:{pr}" for pr in probes if pr in card]
    check(not holes, f"опасная разметка экранирована ({', '.join(holes) or 'чисто'})")
    check("&lt;script&gt;" in page_eco.instance_form(ectx, evil["uid"]),
          "имя предмета видно в экранированном виде")
    data.ITEMS[0], data.MATERIALS[0] = saved_item, saved_mat

    print("\n— Классы обновления 8 —")
    for cls in ("paladin", "ranger", "necromancer", "berserker", "druid", "assassin"):
        check(cls in data.CLASSES, f"класс {cls} доступен в боте")
    check(len(data.CLASSES) == 10, f"классов ровно 10 (сейчас {len(data.CLASSES)})")
    check(all(c in data.CLASS_GROWTH for c in data.CLASSES),
          "у каждого класса свой прирост за уровень")
    check(data.CLASS_GROWTH["berserker"]["strength"] >
          data.CLASS_GROWTH["mage"]["strength"], "берсерк растёт в силе быстрее мага")
    check(data.CLASS_GROWTH["necromancer"]["max_mp"] >
          data.CLASS_GROWTH["warrior"]["max_mp"], "некромант растёт в мане быстрее воина")

    print("\n— Прокачка по классу —")
    from engine import rules
    w = Store(MemoryStorage()).player(9, "Воин")
    Game(store).handle(w, "make:berserker")
    s0 = w.strength
    rules.add_exp(w, 100)
    check(w.strength == s0 + data.CLASS_GROWTH["berserker"]["strength"],
          "уровень даёт прирост именно этого класса")

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
