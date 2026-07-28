"""Лавка и инвентарь: эмодзи-кнопки, страницы, карточки.

python3 tests/test_shop_bag.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import data, itemui, rules  # noqa: E402
from engine.game import Game  # noqa: E402
from engine.storage import Store  # noqa: E402
from webapp.backend import MemoryStorage  # noqa: E402

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


def buttons(reply):
    return [b for row in reply.keyboard for b in row]


def grid_labels(reply):
    """Подписи кнопок-номеров (без навигации и вкладок)."""
    out = []
    for text, act in buttons(reply):
        if isinstance(act, str) and (":" in act) and act.split(":")[0] in (
                "it", "buyc", "sellc"):
            out.append(text)
    return out


def hero(gold=5000):
    store = Store(MemoryStorage())
    game = Game(store)
    p = store.player(1, "Гидеон")
    game.handle(p, "make:warrior")
    p.gold = gold
    return store, game, p


def only_emoji(text):
    """Ни букв, ни «голых» цифр — цифра допустима лишь как keycap-эмодзи.

    Keycap выглядит как «1» + U+FE0F + U+20E3 и рисуется одним значком 1️⃣,
    поэтому такие последовательности вырезаем перед проверкой.
    """
    stripped = ""
    i = 0
    while i < len(text):
        if (i + 2 < len(text) and text[i].isdigit()
                and text[i + 1] == "\ufe0f" and text[i + 2] == "\u20e3"):
            i += 3
            continue
        stripped += text[i]
        i += 1
    return not any(ch.isalpha() or ch.isdigit() for ch in stripped)


def main():
    store, game, p = hero()

    print("\n— Лавка: список —")
    r = game.handle(p, "shop")
    labels = grid_labels(r)
    check(len(labels) == len(data.ITEMS), f"{len(labels)} товаров на кнопках")
    check(all(only_emoji(t) for t in labels),
          "в кнопках только эмодзи — ни букв, ни обычных цифр")
    check(all(t.startswith(itemui.digit(i + 1)) for i, t in enumerate(labels)),
          "кнопки пронумерованы 1️⃣…🔟")
    check(all(rules.item(i)["icon"] in labels[i] for i in range(len(labels))),
          "на кнопке есть иконка товара")
    check(all(rules.item(i)["name"] in r.text for i in range(len(data.ITEMS))),
          "названия товаров — в тексте сообщения")
    check(all(str(rules.item(i)["price"]) in r.text for i in range(len(data.ITEMS))),
          "цены видны в тексте")
    check(max(len(row) for row in r.keyboard) <= itemui.PER_ROW,
          f"не больше {itemui.PER_ROW} кнопок в ряду")

    print("\n— Лавка: вкладки —")
    tabs = [t for t, _ in buttons(r)]
    check(any("Купить" in t for t in tabs), "вкладка «Купить» есть")
    check(any("Продать" in t for t in tabs), "вкладка «Продать» есть")
    sell_tab = next(a for t, a in buttons(r) if "Продать" in t)
    check(sell_tab.startswith("sellbag"), "вкладка ведёт в скупку")

    print("\n— Карточка товара —")
    card = game.handle(p, "buyc:2")
    it = rules.item(2)
    check(it["name"] in card.text, "имя предмета в карточке")
    check("Урон" in card.text and "+10" in card.text, "бонусы расписаны словами")
    check("Редкий" in card.text, "редкость показана")
    check(str(it["price"]) in card.text, "цена показана")
    acts = [a for _, a in buttons(card)]
    check("buy:2" in acts, "кнопка «Купить» ведёт к покупке")
    check(any(a.startswith("shop") for a in acts), "есть возврат в лавку")

    print("\n— Покупка —")
    before = p.gold
    r = game.handle(p, "buy:2")
    check(len(p.inventory) == 1 and p.gold == before - it["price"],
          f"куплено, золото {p.gold}")
    check(it["name"] in r.alert, "всплывашка подтверждает покупку")
    p.gold = 0
    poor = game.handle(p, "buyc:2")
    check(not any(a.startswith("buy:") for _, a in buttons(poor)),
          "без золота кнопки «Купить» нет")
    check("Не хватает" in poor.text, "в карточке видно, сколько не хватает")
    check("Не хватает" in game.handle(p, "buy:2").alert, "покупка без денег отклонена")

    print("\n— Инвентарь: список —")
    store, game, p = hero()
    for i in range(len(data.ITEMS)):
        game.handle(p, f"buy:{i}")
    r = game.handle(p, "bag")
    labels = grid_labels(r)
    check(len(labels) == len(data.ITEMS), "все предметы на кнопках")
    check(all(only_emoji(t) for t in labels), "в сумке кнопки тоже без текста")
    check(all(rules.item(i)["name"] in r.text for i in range(len(data.ITEMS))),
          "названия — в тексте сообщения")

    print("\n— Карточка предмета: надеть / снять —")
    card = game.handle(p, "it:0")
    check(rules.item(0)["name"] in card.text, "карточка открывается по номеру")
    check(any(a == "on:0" for _, a in buttons(card)), "есть кнопка «Надеть»")
    worn = game.handle(p, "on:0")
    check(p.equipped.get("weapon") == 0, "предмет надет")
    check(any(a == "off:0" for _, a in buttons(worn)), "теперь предлагается «Снять»")
    check("Надето" in worn.text, "в карточке отмечено, что надето")
    off = game.handle(p, "off:0")
    check(not p.equipped, "предмет снят")
    check(any(a == "on:0" for _, a in buttons(off)), "снова предлагается «Надеть»")
    again = game.handle(p, "on:0")
    check(p.equipped.get("weapon") == 0 and "Надето" in again.text,
          "предмет можно надеть заново")

    print("\n— Расходник —")
    pos = p.inventory.index(8)
    potion = game.handle(p, f"it:{pos}")
    check(any(a == f"use:{pos}" for _, a in buttons(potion)),
          "у зелья кнопка «Использовать»")
    check(not any(a == f"on:{pos}" for _, a in buttons(potion)),
          "зелье нельзя надеть")
    p.hp = 10
    n = len(p.inventory)
    used = game.handle(p, f"use:{pos}")
    check(p.hp > 10 and len(p.inventory) == n - 1, "зелье выпито и исчезло")
    check("❤️" in used.alert, "во всплывашке видно, сколько восстановлено")

    print("\n— Продажа —")
    store, game, p = hero()
    for i in (0, 2, 3):
        game.handle(p, f"buy:{i}")
    sale = game.handle(p, "sellbag:0")
    labels = grid_labels(sale)
    check(len(labels) == 3, "в скупке видны свои предметы")
    check(all(only_emoji(t) for t in labels), "кнопки скупки без текста")
    check(str(itemui.resale_of(2)) in sale.text, "цена скупки в тексте")
    scard = game.handle(p, "sellc:1")
    check("Варн даёт" in scard.text, "карточка показывает выкуп")
    check(any(a == "sells:1" for _, a in buttons(scard)), "кнопка «Продать» на месте")
    gold, n = p.gold, len(p.inventory)
    sold = game.handle(p, "sells:1")
    check(len(p.inventory) == n - 1 and p.gold > gold, "предмет продан, золото выросло")
    check("скупка" in sold.text, "после продажи остаёмся в лавке")
    check("Продано" in sold.alert, "всплывашка подтверждает продажу")

    print("\n— Продажа надетого —")
    game.handle(p, "on:0")
    check(p.equipped, "предмет надет перед продажей")
    game.handle(p, "sell:0")
    check(not p.equipped, "проданный предмет снялся с героя")

    print("\n— Страницы —")
    store, game, p = hero()
    for i in list(range(10)) + list(range(10)) + [0, 1, 2]:
        game.handle(p, f"buy:{i}")
    check(len(p.inventory) == 23, "в сумке 23 предмета")
    first = game.handle(p, "bag")
    check(len(grid_labels(first)) == itemui.PER_PAGE,
          f"на странице ровно {itemui.PER_PAGE} предметов")
    nav = [a for t, a in buttons(first) if a.startswith("bagp:")]
    check("bagp:1" in nav, "есть переход на вторую страницу")
    check(not any(a == "bagp:-1" for a in nav), "с первой страницы нельзя назад")
    second = game.handle(p, "bagp:1")
    check(grid_labels(second) and "it:10" in [a for _, a in buttons(second)],
          "вторая страница показывает следующие предметы")
    last = game.handle(p, "bagp:2")
    check(len(grid_labels(last)) == 3, "на последней странице остаток")
    check(not any(a == "bagp:3" for _, a in buttons(last)), "дальше последней не уйти")
    check("3/3" in [t for t, _ in buttons(last)], "счётчик страниц виден")
    over = game.handle(p, "bagp:99")
    check(len(grid_labels(over)) == 3, "перелёт номера страницы обрезается")
    back = game.handle(p, "it:20")
    check(any(a == "bagp:2" for _, a in buttons(back)),
          "из карточки возвращаемся на свою страницу")

    print("\n— Пустые состояния —")
    store, game, p = hero(0)
    empty = game.handle(p, "bag")
    check("пуста" in empty.text, "пустая сумка объясняет, что делать")
    check(not grid_labels(empty), "в пустой сумке нет кнопок-номеров")
    check(any(a == "shop" for _, a in buttons(empty)), "предлагает зайти в лавку")
    esale = game.handle(p, "sellbag:0")
    check("нечего продать" in esale.text, "в скупке пусто — понятный текст")

    print("\n— Некорректный ввод —")
    check(game.handle(p, "it:99").alert != "", "нет предмета — всплывашка")
    check(game.handle(p, "use:99").alert != "", "нельзя использовать пустоту")
    check(game.handle(p, "sell:99").alert != "", "нельзя продать пустоту")
    check(game.handle(p, "buyc:99").alert != "", "нет такого товара")
    store, game, p = hero()
    game.handle(p, "buy:8")
    check(game.handle(p, "on:0").alert != "", "зелье нельзя надеть — отказ")
    check(game.handle(p, "off:0").alert != "", "снять ненадетое нельзя")

    print("\n— Нумерация —")
    check(itemui.digit(1) == "1️⃣" and itemui.digit(10) == "🔟", "цифры-эмодзи 1..10")
    check(itemui.pages(0) == 1 and itemui.pages(10) == 1 and itemui.pages(11) == 2,
          "страницы считаются верно")
    check(itemui.clamp(-5, 23) == 0 and itemui.clamp(99, 23) == 2,
          "номер страницы прижимается к границам")

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
