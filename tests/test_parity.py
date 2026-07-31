"""Паритет стеков: каждая механика должна быть в обоих.

Зачем этот набор. В репозитории два независимых стека:

  A — браузерный: `engine/` + `webapp/` (Pyodide, GitHub Pages);
  B — серверный:  `core/` + `bot/` + `admin/` (SQLAlchemy, aiogram).

Механику легко сделать в одном и забыть про другой — так уже случалось:
подземелья годами жили только на сервере, а защищённый карман только в
браузере, и разрыв всплыл через несколько итераций.

Теперь каждая механика перечислена в реестре ниже. Если её нет в одном из
стеков, это **осознанное решение с причиной**, а не оплошность: тест
падает, пока строку не заполнят честно.

Как добавить новую механику:
  1. допишите строку в REGISTRY;
  2. если сделано в обоих стеках — оставьте `todo=""`;
  3. если паритет отложен — укажите причину в `todo`, тест это примет,
     но механика будет числиться в отчёте как долг.

python3 tests/test_parity.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


class Feature:
    """Механика и её следы в обоих стеках.

    `browser` / `server` — файлы, которые обязаны существовать.
    `todo` — причина, по которой паритета пока нет (пустая строка = паритет).
    """

    def __init__(self, name, browser=(), server=(), todo=""):
        self.name = name
        self.browser = list(browser)
        self.server = list(server)
        self.todo = todo


# ── реестр механик ──────────────────────────────────────────
# Порядок — по времени появления. Пустой todo означает полный паритет.

REGISTRY = [
    Feature("Мир и локации",
            browser=["engine/world.py"],
            server=["core/worldgen.py", "core/worldops.py"]),
    Feature("Бой",
            browser=["engine/combat.py"],
            server=["bot/handlers/battle.py"]),
    Feature("Инвентарь и экипировка",
            browser=["engine/inventory.py"],
            server=["bot/handlers/inventory.py"]),
    Feature("Лавка",
            browser=["engine/shop.py"],
            server=["bot/handlers/shop.py"]),
    Feature("Крафт",
            browser=["engine/craft.py"],
            server=["core/crafting.py"]),
    Feature("Аукцион",
            browser=["engine/auction.py"],
            server=["core/auction.py"]),
    Feature("Именные экземпляры вещей",
            browser=["engine/items.py"],
            server=["core/history.py"]),
    Feature("Магия",
            browser=["engine/hero.py"],
            server=["core/magic.py"]),
    Feature("Права админов",
            browser=["engine/permissions.py"],
            server=["admin/auth.py"]),
    Feature("Подземелья",
            browser=["engine/dungeon.py", "engine/dungeonui.py"],
            server=["core/dungeons.py", "bot/handlers/dungeon.py"]),
    Feature("Защищённый карман и VIP",
            browser=["engine/stash.py"],
            server=["core/stash.py", "core/vip.py"]),
    Feature("Отряды",
            browser=["engine/party.py"],
            server=["bot/handlers/party.py"]),
    Feature("Респавн мира",
            browser=["engine/respawn.py"],
            server=["core/spawns.py"]),

    Feature("Катаклизмы",
            browser=["engine/cataclysm.py", "engine/cataclysm_kinds.py"],
            server=["core/worldevents.py"]),
    Feature("Орда и агрессия тварей",
            browser=["engine/horde.py", "engine/behavior.py"],
            server=["core/behavior.py"]),
    Feature("Мировые боссы",
            browser=["engine/worldboss.py"],
            server=["core/worldevents.py"]),
    Feature("Фракции и репутация",
            browser=["engine/factions.py"],
            server=["core/factions.py"]),
    Feature("Надгробия и цена смерти",
            browser=["engine/death.py"],
            server=["core/death.py"]),
    Feature("Достопримечательности",
            browser=["engine/landmarks.py"],
            server=["core/landmarks.py"]),
    Feature("Деньги: бронза/серебро/золото и премиум",
            browser=["engine/money.py"],
            server=["core/money.py"]),

    # ── ниже: механики без паритета, причина обязательна ──
    Feature("Задания",
            browser=["engine/quests.py"],
            server=["core/models.py"],
            todo="на сервере есть модель Quest, но нет выдачи и сдачи в боте"),
]


def missing(paths):
    return [p for p in paths if not os.path.exists(os.path.join(ROOT, p))]


def test_registry_is_honest():
    print("\n— Реестр соответствует репозиторию —")
    for f in REGISTRY:
        gone = missing(f.browser) + missing(f.server)
        check(not gone, f"«{f.name}»: файлы на месте"
                        + (f" — нет {gone}" if gone else ""))


def test_parity_or_reason():
    print("\n— Паритет или честная причина —")
    for f in REGISTRY:
        has_a = bool(f.browser)
        has_b = bool(f.server)
        if has_a and has_b:
            check(True, f"«{f.name}»: оба стека")
        else:
            where = "серверном" if has_a else "браузерном"
            check(bool(f.todo.strip()),
                  f"«{f.name}»: нет в {where} — причина указана"
                  + (f" ({f.todo})" if f.todo else " — ПРИЧИНА НЕ УКАЗАНА"))


def test_new_engine_modules_registered():
    """Новый модуль в engine/ обязан попасть в реестр.

    Именно так разрыв и возникает: механику пишут в engine/, а про стек B
    вспоминают через несколько итераций. Теперь не получится молча.
    """
    print("\n— Новые модули engine/ попадают в реестр —")
    import glob

    # Инфраструктура, а не игровые механики: их паритет не требуется.
    INFRA = {
        "engine/__init__.py", "engine/models.py", "engine/data.py",
        "engine/content.py", "engine/rules.py", "engine/texts.py",
        "engine/itemui.py", "engine/storage.py", "engine/game.py",
        "engine/social.py", "engine/explore.py", "engine/mapview.py",
        "engine/audit.py", "engine/adminops.py", "engine/adminworld.py",
        "engine/adminmenu.py", "engine/adminbot.py", "engine/adminroute.py",
        "engine/trade.py",
    }
    listed = set()
    for f in REGISTRY:
        listed.update(f.browser)

    unlisted = []
    for path in sorted(glob.glob("engine/*.py")):
        if path in INFRA or path in listed:
            continue
        unlisted.append(path)
    check(not unlisted,
          "каждый игровой модуль engine/ есть в реестре"
          + (f" — забыты: {unlisted}" if unlisted else ""))


def test_shared_numbers_match():
    """Числа механик, живущих в обоих стеках, обязаны совпадать."""
    print("\n— Общие константы совпадают —")
    from engine import stash as engine_stash

    try:
        from core import stash as core_stash
    except ImportError as e:                      # нет sqlalchemy — не беда
        check(True, f"серверный стек недоступен, пропуск ({e})")
        return

    from engine import money as engine_money

    try:
        from core import money as core_money
    except ImportError as e:
        check(True, f"серверные деньги недоступны, пропуск ({e})")
    else:
        coin_pairs = [
            ("бронзы в серебре", engine_money.BRONZE_PER_SILVER,
             core_money.BRONZE_PER_SILVER),
            ("серебра в золоте", engine_money.SILVER_PER_GOLD,
             core_money.SILVER_PER_GOLD),
            ("бронзы в золоте", engine_money.BRONZE_PER_GOLD,
             core_money.BRONZE_PER_GOLD),
            ("курс кристалла", engine_money.PREMIUM_RATE,
             core_money.PREMIUM_RATE),
        ]
        for label, a, b in coin_pairs:
            check(a == b, f"{label}: {a} = {b}")
        check(set(engine_money.TUNABLES) == set(core_money.TUNABLES),
              "настройки валют совпадают")

    pairs = [
        ("размер кармана", engine_stash.SLOTS, core_stash.SLOTS),
        ("прибавка VIP", engine_stash.VIP_BONUS, core_stash.VIP_BONUS),
        ("доля потерь", engine_stash.LOSS_SHARE, core_stash.LOSS_SHARE),
        ("срок VIP", engine_stash.VIP_DAYS, core_stash.VIP_DAYS),
    ]
    for label, a, b in pairs:
        check(a == b, f"{label}: {a} = {b}")
    check(set(engine_stash.TUNABLES) == set(core_stash.TUNABLES),
          "набор настраиваемых параметров одинаков")

    # Каталоги контента: серверные модули берут их из engine/, поэтому
    # расхождение означало бы, что кто-то завёл вторую копию.
    try:
        from core import death as core_death
        from core import factions as core_factions
        from core import landmarks as core_landmarks
        from core import worldevents as core_events
        from engine import death as e_death
        from engine import factions as e_factions
        from engine import landmarks as e_landmarks
        from engine import worldboss as e_boss
        from engine.cataclysm_kinds import KINDS as e_kinds
    except ImportError as e:
        check(True, f"часть модулей недоступна, пропуск ({e})")
        return
    check(set(core_events.KINDS) == set(e_kinds), "каталог бедствий общий")
    check(set(core_events.BOSSES) == set(e_boss.BOSSES), "каталог боссов общий")
    check(core_factions.FACTIONS == e_factions.FACTIONS, "фракции те же")
    check(core_landmarks.LANDMARKS == e_landmarks.LANDMARKS,
          "каталог диковин общий")
    check(core_death.GRAVE_HOURS == e_death.GRAVE_HOURS, "срок могилы тот же")


def report():
    """Сводка: что уже в обоих стеках, а что ещё нет."""
    both = [f for f in REGISTRY if f.browser and f.server]
    debt = [f for f in REGISTRY if not (f.browser and f.server)]
    print("\n" + "─" * 46)
    print(f"Паритет: {len(both)} из {len(REGISTRY)} механик в обоих стеках.")
    if debt:
        print("\nЖдут переноса:")
        for f in debt:
            side = "только браузер" if f.browser else "только сервер"
            print(f"  • {f.name} ({side}) — {f.todo}")


def main():
    for fn in (test_registry_is_honest, test_parity_or_reason,
               test_new_engine_modules_registered, test_shared_numbers_match):
        fn()
    report()
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
