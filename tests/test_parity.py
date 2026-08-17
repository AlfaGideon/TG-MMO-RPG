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
    Feature("Бродячий торговец",
            browser=["engine/merchant.py"],
            server=["core/merchant.py"]),
    Feature("Угловые замки 25×25",
            browser=["engine/world.py"],
            server=["core/worldgen.py", "core/seed.py"]),
    Feature("Расширенные статы и Gear Score",
            browser=["engine/stats.py"],
            server=["core/stats.py"]),
    Feature("Полноразмерные слизевые монстры",
            browser=["engine/content.py", "engine/combat.py"],
            server=["core/mob_images.py", "bot/handlers/battle.py"]),
    Feature("Карма",
            browser=["engine/karma.py"],
            server=["core/karma.py"]),
    Feature("Знамения",
            browser=["engine/omens.py"],
            server=["core/omens.py"]),
    Feature("Реактивные реплики жителей",
            browser=["engine/dialogue.py"],
            server=["core/dialogue.py"]),
    Feature("Титулы",
            browser=["engine/titles.py"],
            server=["core/titles.py"]),
    Feature("Бестиарий",
            browser=["engine/bestiary.py"],
            server=["core/bestiary.py"]),
    Feature("Фазы луны",
            browser=["engine/lunar.py"],
            server=["core/lunar.py"]),
    Feature("Перерождение",
            browser=["engine/prestige.py"],
            server=["core/prestige.py"]),
    Feature("Таланты",
            browser=["engine/talents.py"],
            server=["core/talents.py"]),
    Feature("Подклассы",
            browser=["engine/subclasses.py"],
            server=["core/subclasses.py"]),
    Feature("Фамильяры",
            browser=["engine/familiars.py"],
            server=["core/familiars.py"]),
    Feature("Шаблоны питомцев (каталог для панелей)",
            browser=["engine/pets.py"],
            server=["core/pets.py"]),
    Feature("Руны и рунические слова",
            browser=["engine/runes.py"],
            server=["core/runes.py"]),
    Feature("Мирные занятия",
            browser=["engine/gathering.py"],
            server=["core/gathering.py", "core/archaeology.py"]),
    Feature("Звуковой эмбиент",
            browser=["engine/ambient.py"],
            server=["core/ambient.py"]),
    Feature("Разбор снаряжения",
            browser=["engine/salvage.py"],
            server=["core/salvage.py"]),
    Feature("Призрачный торговец и прах",
            browser=["engine/spectral.py"],
            server=["core/spectral.py"]),
    Feature("Зал Славы",
            browser=["engine/legends.py"],
            server=["core/legends.py"]),
    Feature("Ломбард",
            browser=["engine/shadowecon.py"],
            server=["core/pawnshop.py"]),
    Feature("Вклады в лавки",
            browser=["engine/shadowecon.py"],
            server=["core/investments.py"]),
    Feature("Чёрный рынок",
            browser=["engine/shadowecon.py"],
            server=["core/blackmarket.py"]),
    Feature("Колизей Теней",
            browser=["engine/arena.py"],
            server=["core/arena.py"]),
    Feature("Гильдии",
            browser=["engine/guilds.py"],
            server=["core/guilds.py"]),
    Feature("Наставничество",
            browser=["engine/guilds.py"],
            server=["core/mentorship.py"]),
    Feature("Награды за головы",
            browser=["engine/bounty.py"],
            server=["core/bounty.py"]),
    Feature("Иллюзорные стены",
            browser=["engine/illusions.py"],
            server=["core/illusions.py"]),

    Feature("Трёхвалютная экономика",
            browser=["engine/currency.py"],
            server=["core/models.py", "bot/utils/texts.py"]),

    # ── ниже: механики без паритета, причина обязательна ──

    Feature("Задания",
            browser=["engine/quests.py"],
            server=["core/quests.py", "bot/handlers/quests.py"]),
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
        # slots.py — не механика, а способ хранения экипировки внутри
        # браузерного стека (какая именно вещь надета). На сервере тот же
        # вопрос решён иначе: InventoryItem.is_equipped у конкретной строки,
        # поэтому переносить модуль в core/ нечего.
        "engine/slots.py",
        # progress.py — экраны прогресса, вынесенные из game.py ради
        # лимита в 500 строк; сами механики зарегистрированы отдельно.
        "engine/progress.py",
        "engine/social_ui.py",
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

    pairs = [
        ("размер кармана", engine_stash.SLOTS, core_stash.SLOTS),
        ("прибавка VIP", engine_stash.VIP_BONUS, core_stash.VIP_BONUS),
        ("доля потерь", engine_stash.LOSS_SHARE, core_stash.LOSS_SHARE),
        ("срок VIP", engine_stash.VIP_DAYS, core_stash.VIP_DAYS),
    ]
    try:
        from engine import merchant as e_merchant
        from core import merchant as c_merchant
    except ImportError as e:
        check(True, f"торговец недоступен, пропуск ({e})")
        return
    pairs += [
        ("наценка торговца", e_merchant.MARKUP, c_merchant.MARKUP),
        ("шанс встречи торговца", e_merchant.WANDER_CHANCE, c_merchant.WANDER_CHANCE),
        ("срок торговли, сек", e_merchant.LIFETIME, c_merchant.LIFETIME_HOURS * 3600),
        ("потолок витрины", e_merchant.MAX_WARES, c_merchant.MAX_WARES),
    ]
    for label, a, b in pairs:
        check(a == b, f"{label}: {a} = {b}")
    check(set(engine_stash.TUNABLES) == set(core_stash.TUNABLES),
          "набор настраиваемых параметров одинаков")

    # Карма: пороги, дельты поступков и эффекты обязаны совпадать в обоих
    # стеках, иначе один и тот же поступок даёт разный моральный путь.
    try:
        from engine import karma as e_karma
        from core import karma as c_karma
    except ImportError as e:
        check(True, f"карма недоступна, пропуск ({e})")
        return
    karma_pairs = [
        ("максимум кармы", e_karma.MAX_KARMA, c_karma.MAX_KARMA),
        ("минимум кармы", e_karma.MIN_KARMA, c_karma.MIN_KARMA),
        ("порог Благочестивого", e_karma.PIOUS_KARMA, c_karma.PIOUS_KARMA),
        ("порог Осквернителя", e_karma.DEFILED_KARMA, c_karma.DEFILED_KARMA),
        ("карма за нежить", e_karma.KILL_UNDEAD, c_karma.KILL_UNDEAD),
        ("карма за босса", e_karma.KILL_BOSS, c_karma.KILL_BOSS),
        ("карма за могилу", e_karma.GRAVE_LOOT, c_karma.GRAVE_LOOT),
        ("бонус лечения", e_karma.HEAL_BONUS, c_karma.HEAL_BONUS),
        ("бонус Тьмы", e_karma.DARK_DAMAGE_BONUS, c_karma.DARK_DAMAGE_BONUS),
    ]
    for label, a, b in karma_pairs:
        check(a == b, f"карма: {label}: {a} = {b}")
    check(e_karma.UNDEAD == c_karma.UNDEAD, "карма: список нежити совпадает")

    # Деньги: серверный стек считает тем же модулем, что и движок, — если
    # кто-то заведёт вторую копию с другим курсом, это всплывёт здесь.
    # Титулы, бестиарий, луна и перерождение: каталоги и пороги общие —
    # core-модули реэкспортируют engine, но проверим это явно.
    try:
        from core import bestiary as c_bestiary
        from core import lunar as c_lunar
        from core import prestige as c_prestige
        from core import titles as c_titles
        from engine import bestiary as e_bestiary
        from engine import lunar as e_lunar
        from engine import prestige as e_prestige
        from engine import titles as e_titles
        check(c_titles.TITLES_CATALOG == e_titles.TITLES_CATALOG,
              "каталог титулов общий")
        check(c_lunar.PHASES == e_lunar.PHASES, "каталог фаз луны общий")
        check(c_bestiary.get_mob_slayer_bonus is e_bestiary.get_mob_slayer_bonus,
              "бонус охотника считается одним кодом")
        check(c_prestige.REBIRTH_MIN_LEVEL == e_prestige.REBIRTH_MIN_LEVEL,
              f"порог перерождения: {e_prestige.REBIRTH_MIN_LEVEL}")
        from core import familiars as c_fam
        from core import subclasses as c_subs
        from core import talents as c_tal
        from engine import familiars as e_fam
        from engine import subclasses as e_subs
        from engine import talents as e_tal
        check(c_tal.TALENT_STARS is e_tal.TALENT_STARS, "древо талантов общее")
        check(c_subs.SUBCLASSES is e_subs.SUBCLASSES, "каталог подклассов общий")
        check(c_fam.FAMILIARS is e_fam.FAMILIARS, "каталог фамильяров общий")
        from core import pets as c_pets
        from engine import pets as e_pets
        check(c_pets.RARITIES is e_pets.RARITIES,
              "шкала редкости шаблонов питомцев общая")
        check(c_pets.normalize_key is e_pets.normalize_key,
              "ключ шаблона питомца нормализуется одним кодом")
        check(c_pets.normalize_bonuses is e_pets.normalize_bonuses,
              "бонусы шаблона валидируются одним кодом")
        from core import ambient as c_amb
        from core import runes as c_runes
        from engine import ambient as e_amb
        from engine import gathering as e_gath
        from engine import runes as e_runes
        check(c_runes.RUNES is e_runes.RUNES, "каталог рун общий")
        check(c_runes.RUNEWORDS is e_runes.RUNEWORDS, "рунические слова общие")
        check(c_amb.AMBIENT_PROFILES is e_amb.AMBIENT_PROFILES,
              "профили эмбиента общие")
        check(e_gath.FRAGMENTS_FOR_MAP == 5,
              f"осколков до карты: {e_gath.FRAGMENTS_FOR_MAP}")
        from core import salvage as c_salv
        from core import spectral as c_spec
        from engine import salvage as e_salv
        from engine import spectral as e_spec
        check(c_spec.SPECTRAL_WARES is e_spec.SPECTRAL_WARES,
              "витрина призрака общая")
        check(c_salv.S is e_salv,
              "разбор считается общей таблицей")
        from core import investments as c_inv
        from core import pawnshop as c_pawn
        from engine import shadowecon as e_econ
        check(c_pawn.E is e_econ, "ломбард берёт ставки из engine/shadowecon")
        check(c_inv.DIVIDEND_RATE == e_econ.DIVIDEND_RATE,
              f"ставка дивидендов: {e_econ.DIVIDEND_RATE}")
        check(e_econ.buyback_for(e_econ.loan_for(100)) > e_econ.loan_for(100),
              "выкуп всегда дороже займа")
        check(e_econ.liquidated_price_for(100) > 100,
              "изъятое перепродаётся с наценкой")
        from core import arena as c_arena
        from core import bounty as c_bounty
        from core import guilds as c_guilds  # noqa: F401
        from core import mentorship as c_ment
        from engine import arena as e_arena
        from engine import bounty as e_bounty
        from engine import guilds as e_guilds
        check(c_arena.A is e_arena, "арена берёт награды из engine/arena")
        check(c_bounty.B is e_bounty, "награды за головы общие")
        check(c_ment.G is e_guilds, "наставничество берёт пороги из engine/guilds")
        check(e_arena.WIN_TOKENS > e_arena.LOSS_TOKENS,
              "победа на арене выгоднее поражения")
        check(c_subs.SUBCLASS_MIN_LEVEL == e_subs.SUBCLASS_MIN_LEVEL,
              f"порог специализации: {e_subs.SUBCLASS_MIN_LEVEL}")
    except ImportError as e:
        check(True, f"часть модулей недоступна, пропуск ({e})")

    from engine import currency as e_currency
    check(e_currency.CONVERSION == 100, f"курс 1:100 ({e_currency.CONVERSION})")
    probe_engine = type("P", (), {"bronze": 99, "silver": 0, "gold": 0})()
    e_currency.add_currency(probe_engine, bronze=1)
    check((probe_engine.bronze, probe_engine.silver) == (0, 1),
          "99🟤 + 1🟤 сворачивается в 1⚪")
    check(e_karma.DARK_SCHOOL == c_karma.DARK_SCHOOL, "карма: школа Тьмы одна")

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
    try:
        from core import omens as core_omens
        from engine import omens as e_omens
        check(core_omens.OMENS == e_omens.OMENS, "каталог знамений общий")
    except ImportError as e:
        check(True, f"знамения недоступны, пропуск ({e})")


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
