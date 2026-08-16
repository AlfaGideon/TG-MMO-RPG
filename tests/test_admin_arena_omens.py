"""Остаток админки и шаблоны питомцев: пункты № 20, 67–70, 86.

python3 tests/test_admin_arena_omens.py

Что закрывается:

* **№ 67** — `core/arena.py` и `core/duels.py` не упоминались в
  `admin/main.py` ни разу: рейтинги Колизея видел только сам игрок.
  Попутно найден баг: вызов на дуэль (`world_extra.duel_invites`) висел
  вечно — принять его можно было и через сутки. Добавлен TTL.
* **№ 68** — знамения правились только в коде; теперь свои знамения
  хранятся в `AppSetting` и подмешиваются к каталогу.
* **№ 69** — престиж, титулы, подкласс и таланты в карточке игрока.
* **№ 70** — карма, ломбард, вклады, дивиденды и знамения публикуются
  в живую ленту (`core/realtime`), у ленты появился фильтр по типам.
* **№ 86** — знамение при живом бедствии показывает ЕГО предвестие:
  поле `omen` у каждого вида в `engine/cataclysm_kinds.KINDS` было
  написано давно, но не читалось нигде.
* **№ 20** — `engine/pets.py`: правила каталога шаблонов питомцев стали
  общими для серверной админки и Pyodide-панели.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Грейсфул-скип: часть проверок требует серверного стека (см. tests/_deps.py).
from _deps import require  # noqa: E402

require("sqlalchemy", "aiosqlite", "aiogram", "fastapi", "jinja2")

# Детерминизм (пункт № 5).
from _seed import pin  # noqa: E402

pin(117)

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


def test_duel_invites_expire():
    """№ 67: зависший вызов на дуэль отсеивается и снимается вручную."""
    print("\n№ 67 — вызовы на дуэль не висят вечно")
    import time

    from bot.handlers import world_extra as WE

    WE.duel_invites.clear()
    check(WE.DUEL_INVITE_TTL > 0, f"TTL вызова задан ({WE.DUEL_INVITE_TTL} с)")

    now = time.time()
    WE.duel_invites[1] = (111, 100, now)               # свежий
    WE.duel_invites[2] = (222, 0, now - WE.DUEL_INVITE_TTL - 5)   # протух

    removed = WE.prune_duel_invites(now)
    check(removed == 1, "протухший вызов убран, свежий остался")
    check(2 not in WE.duel_invites and 1 in WE.duel_invites,
          "убран именно старый вызов")

    pending = WE.pending_duels(now)
    check(len(pending) == 1 and pending[0]["target_id"] == 1,
          "pending_duels отдаёт живой вызов админке")
    check(pending[0]["wager"] == 100, "ставка видна в списке")
    check(0 < pending[0]["expires_in"] <= WE.DUEL_INVITE_TTL,
          "показан остаток времени жизни вызова")

    check(WE.cancel_duel_invite(1) is True, "ручная отмена снимает вызов")
    check(WE.cancel_duel_invite(1) is False, "повторная отмена возвращает False")
    WE.duel_invites.clear()


def test_admin_mentions_arena_and_progress():
    """№ 67 и № 69: админка знает про арену, дуэли и эндгейм-прогресс."""
    print("\n№ 67, 69 — админка ссылается на модули, о которых молчала")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "admin", "main.py"), encoding="utf-8") as fh:
        main_src = fh.read()

    check("CharacterShadow" in main_src, "админка читает тени арены")
    check("engine import arena" in main_src or "engine.arena" in main_src,
          "числа арены берутся из engine/arena, а не переписаны")
    check("cancel_duel_invite" in main_src, "есть отмена зависшей дуэли")
    for mod in ("prestige", "titles", "subclasses", "talents"):
        check(f"core import {mod}" in main_src or f"core.{mod}" in main_src,
              f"карточка игрока читает core/{mod}.py")
    check("/player/{char_id}/reset-talents" in main_src,
          "есть сброс созвездий одной кнопкой")

    tpl_dir = os.path.join(root, "admin", "templates")
    with open(os.path.join(tpl_dir, "battles.html"), encoding="utf-8") as fh:
        battles = fh.read()
    check("Колизей Теней" in battles, "секция арены на /battles")
    check("arena_rows" in battles and "duel_rows" in battles,
          "выводятся и рейтинги, и активные вызовы")

    with open(os.path.join(tpl_dir, "player_detail.html"), encoding="utf-8") as fh:
        detail = fh.read()
    for word in ("Перерождение", "Титул", "Подкласс", "Созвездия"):
        check(word in detail, f"в карточке игрока есть блок «{word}»")


def test_omens_editor_and_custom_catalog():
    """№ 68: свои знамения подмешиваются к общему каталогу."""
    print("\n№ 68 — редактор знамений")
    from engine import omens

    base = len(omens.OMENS)
    settings = {}
    check(len(omens.catalog(settings)) == base,
          f"без добавок каталог не меняется ({base})")

    settings[omens.CUSTOM_KEY] = [
        {"icon": "🕯", "title": "Вой в тумане", "desc": "Псы воют к беде."},
        {"desc": "запись без заголовка"},          # мусор
        "строка вместо словаря",                    # мусор
    ]
    custom = omens.custom_omens(settings)
    check(len(custom) == 1, "битые записи отброшены, осталась одна")
    check(custom[0]["title"] == "Вой в тумане", "своё знамение прочитано")
    check(len(omens.catalog(settings)) == base + 1, "каталог вырос на одно")

    # Сервер хранит JSON-строкой — та же функция должна её понимать.
    import json

    settings_json = {omens.CUSTOM_KEY: json.dumps(settings[omens.CUSTOM_KEY][:1],
                                                  ensure_ascii=False)}
    check(len(omens.custom_omens(settings_json)) == 1,
          "JSON-строка из AppSetting разбирается тем же кодом")
    check(omens.custom_omens({omens.CUSTOM_KEY: "не json"}) == [],
          "битый JSON не роняет экран")

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tpl = os.path.join(root, "admin", "templates", "editor_omens.html")
    check(os.path.exists(tpl), "шаблон страницы /editor/omens существует")


def test_omens_follow_cataclysms():
    """№ 86: при живом бедствии знамение указывает именно на него."""
    print("\n№ 86 — знамения привязаны к бедствиям")
    from engine import omens
    from engine.cataclysm_kinds import KINDS

    quake = omens.for_cataclysm("quake")
    check(quake is not None, "у землетрясения есть предвестие")
    check(quake["desc"] == KINDS["quake"]["omen"],
          "текст взят из описания бедствия, а не написан заново")
    check(omens.for_cataclysm("нет_такого") is None,
          "неизвестный вид не выдумывает знамение")

    rows = omens.get_current_omens(None, ["wildfire"])
    check(rows[0]["kind"] == "wildfire",
          "предвестие бушующего бедствия идёт первым")
    check(len(rows) == len(omens.OMENS) + 1,
          "каталог при этом никуда не делся")

    banner = omens.omen_banner(None, ["wildfire"])
    check("Пожар" in banner, "баннер показывает именно это бедствие")

    quiet = omens.get_current_omens()
    check(all("kind" not in o for o in quiet),
          "в спокойное время предвестий бедствий нет")

    # Браузерный движок должен подхватывать живое бедствие сам.
    from engine import cataclysm, storage
    from webapp.backend import MemoryStorage

    store = storage.Store(MemoryStorage())
    store.load()
    cataclysm.strike(store, "quake", 0)
    kinds = [e["kind"] for e in cataclysm.active(store, 0) if e.get("kind")]
    check("quake" in kinds, "бедствие бушует в браузерном стеке")
    text = omens.omens_text(store.settings, kinds)
    check("Землетрясение" in text, "экран знамений движка показывает предвестие")


def test_realtime_knows_new_subsystems():
    """№ 70: события подсистем публикуются и форматируются."""
    print("\n№ 70 — живая лента знает новые подсистемы")
    from core import realtime as RT

    cases = {
        "karma_changed": ({"name": "Гидеон", "delta": -3, "value": -153,
                           "icon": "💀", "title": "Осквернитель",
                           "path_changed": True}, "карма"),
        "pawn_loan": ({"name": "Гидеон", "item": "Меч", "loan_bronze": 140,
                       "buyback_price": 161}, "заложил"),
        "town_invested": ({"name": "Гидеон", "location_name": "Погост",
                           "amount": 500}, "вложил"),
        "dividends_paid": ({"count": 3, "total": 60}, "дивиденды"),
        "omen_shown": ({"name": "Гидеон", "title": "Предвестие: Пожар",
                        "cataclysm": "wildfire"}, "знамение"),
    }
    for etype, (payload, word) in cases.items():
        text = RT.format_radar_event({"type": etype, "payload": payload, "ts": 0})
        check(word in text, f"{etype} → человеческая строка «{word}»")
        check("Событие мира:" not in text,
              f"{etype} не падает в общую заглушку")

    # Карма публикует событие сама — хендлерам ничего дописывать не нужно.
    from core import karma as core_karma

    RT.clear()

    class FakeChar:
        id = 1
        name = "Гидеон"
        karma_score = 0

    ch = FakeChar()
    core_karma.change_karma(ch, -160)
    hist = [e for e in RT.get_history(limit=10) if e["type"] == "karma_changed"]
    check(len(hist) == 1, "смена кармы попала в ленту")
    check(hist[0]["payload"]["path_changed"] is True,
          "пересечение порога отмечено отдельно")

    before = len(RT.get_history(limit=50))
    core_karma.change_karma(ch, 0)
    check(len(RT.get_history(limit=50)) == before,
          "нулевое изменение ленту не засоряет")

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "admin", "templates", "dashboard.html"),
              encoding="utf-8") as fh:
        dash = fh.read()
    check("data-feed-filter" in dash, "у ленты есть фильтр по категориям")
    for group in ("karma_changed", "pawn_loan", "town_invested", "omen_shown"):
        check(group in dash, f"фильтр знает тип {group}")


def test_pet_templates_shared_rules():
    """№ 20: правила каталога питомцев общие для обоих стеков."""
    print("\n№ 20 — шаблоны питомцев")
    from core import pets as c_pets
    from engine import pets as e_pets

    check(c_pets.RARITIES is e_pets.RARITIES, "шкала редкости — один объект")
    check(c_pets.normalize_key is e_pets.normalize_key,
          "нормализация ключа — один код")
    check(c_pets.normalize_bonuses is e_pets.normalize_bonuses,
          "валидация бонусов — один код")

    from engine.storage import Store
    from webapp.backend import MemoryStorage

    store = Store(MemoryStorage())
    tpl = e_pets.add(store, name="Слизень Зари", family="slime",
                     rarity="rare", bonuses='{"crit_bonus": 3}')
    check(tpl["key"] == "слизень_зари", f"ключ собран из имени ({tpl['key']})")
    check(len(e_pets.templates(store)) == 1, "шаблон сохранён")

    e_pets.add(store, name="Слизень Зари", rarity="epic")
    check(len(e_pets.templates(store)) == 1,
          "повтор ключа перезаписывает запись, а не плодит дубли")

    try:
        e_pets.add(store, name="   ")
        check(False, "пустое имя должно отвергаться")
    except ValueError:
        check(True, "пустое имя отвергается с понятной ошибкой")

    try:
        e_pets.add(store, name="Тест", bonuses="не json")
        check(False, "битый JSON должен отвергаться")
    except Exception as exc:
        check("JSON" in type(exc).__name__ or isinstance(exc, ValueError),
              "битый JSON бонусов отвергается")

    check(e_pets.toggle(store, "слизень_зари") is False, "шаблон выключается")
    check(e_pets.toggle(store, "нет_такого") is None,
          "переключение несуществующего ключа возвращает None")
    check(e_pets.remove(store, "слизень_зари") is True, "шаблон удаляется")
    check(e_pets.remove(store, "слизень_зари") is False,
          "повторное удаление возвращает False")

    check("пока декоративный" in e_pets.describe_bonuses('{"mystery": 1}'),
          "неизвестный бонус помечается как декоративный")
    check(e_pets.describe_bonuses("сломано") == "без бонусов",
          "битые бонусы не роняют карточку")

    # Панель показывает вкладку.
    from webapp.pages import content

    class Ctx:
        def __init__(self):
            self.store = Store(MemoryStorage())
            self.state = {"content_tab": "pet_templates"}

    ctx = Ctx()
    e_pets.add(ctx.store, name="Пепельный ворон", family="bird", rarity="epic")
    html = content.render(ctx)
    check("Пепельный ворон" in html, "шаблон виден в Pyodide-панели")
    check("🟣" in html, "редкость показана значком из общего каталога")


def main():
    test_duel_invites_expire()
    test_admin_mentions_arena_and_progress()
    test_omens_editor_and_custom_catalog()
    test_omens_follow_cataclysms()
    test_realtime_knows_new_subsystems()
    test_pet_templates_shared_rules()

    print("\n" + "=" * 46)
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}")
        for f in FAILED:
            print("   -", f)
        return 1
    print("✅ Админка видит арену, знамения и прогресс; питомцы в паритете")
    return 0


if __name__ == "__main__":
    sys.exit(main())
