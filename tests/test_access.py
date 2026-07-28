"""Права доступа, карта и контент: python3 tests/test_access.py"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Заглушки браузерных модулей (в браузере их даёт Pyodide).
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

from engine import adminbot, data, mapview, permissions  # noqa: E402
from engine.game import Game  # noqa: E402
from engine.storage import Store  # noqa: E402
from webapp.actions import content_actions as ca  # noqa: E402
from webapp.backend import MemoryStorage  # noqa: E402
from webapp.pages import content as page_content  # noqa: E402
from webapp.pages import dungeons as page_dungeons  # noqa: E402
from webapp.pages import players as page_players  # noqa: E402

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


class Ctx:
    def __init__(self, store):
        self.store = store
        self.state = {}

    def close_modal(self):
        pass

    def render(self):
        pass


class FakeDom:
    vals = {}

    @staticmethod
    def value(sel, default=""):
        return FakeDom.vals.get(sel, default)

    @staticmethod
    def toast(*a, **k):
        pass

    @staticmethod
    def el(sel):
        return None


def main():
    store = Store(MemoryStorage())
    game = Game(store)
    p = store.player(555, "Гидеон")
    game.handle(p, "make:mage")

    print("\n— Права доступа —")
    check(not p.is_web_admin, "по умолчанию доступа нет")
    check(game.handle(p, "admin").alert != "", "без доступа админка закрыта")
    menu = lambda: [b[0] for row in game.handle(p, "menu").keyboard for b in row]
    check(not any("Админка" in t for t in menu()), "кнопки «Админка» нет в меню")

    caps = [c for c in permissions.rank_caps("gamemaster") if c != "broadcast"]
    adminbot.grant(store, p, "gamemaster", caps)
    check(any("Админка" in t for t in menu()), "после выдачи кнопка появилась в боте")
    check(len(p.web_admin_password) >= 8, "пароль сгенерирован при выдаче")
    check(permissions.can(p, "edit_world"), "выданное право работает")
    check(not permissions.can(p, "broadcast"), "снятое право не действует")
    check(not permissions.can(p, "grant_admin"), "чужое право недоступно")

    txt = game.handle(p, "adminpass").text
    check(p.web_admin_password in txt, "пароль виден игроку в боте")
    check("Гейм-мастер" in game.handle(p, "admin").text, "ранг показан в боте")

    for rank in permissions.RANK_KEYS:
        check(bool(permissions.rank_caps(rank)), f"ранг {rank} имеет пресет прав")
    check(set(permissions.rank_caps("admin")) == set(permissions.CAP_KEYS),
          "у админа все права")

    adminbot.revoke(store, p)
    check(not any("Админка" in t for t in menu()), "после отзыва кнопка убрана")
    check(not p.web_admin_password, "пароль стёрт при отзыве")

    print("\n— Форма выдачи прав в панели —")
    adminbot.grant(store, p, "moderator")
    form = page_players.access_form(Ctx(store), 555)
    check(form.count("type='checkbox'") == len(permissions.CAP_KEYS),
          f"в форме {len(permissions.CAP_KEYS)} галочек по функциям")
    check(p.web_admin_password in form, "пароль показан в панели")
    check("access-save" in form and "access-revoke" in form, "кнопки выдачи и отзыва")

    print("\n— Карта игрока —")
    r = game.handle(p, "map")
    check("🔴" in r.text, "игрок отмечен точкой")
    check("⬜" in r.text, "непройденное скрыто туманом")
    for bad in ("#", "@", " . "):
        check(bad not in r.text, f"на карте нет символа {bad.strip() or 'точки'}")
    before = r.text.count("⬜")
    for d in ("n", "e", "s", "w"):
        game.handle(p, f"go:{d}")
    check(game.handle(p, "map").text.count("⬜") <= before,
          "туман рассеивается по мере исследования")
    check("Обновить" in str(game.handle(p, "map").keyboard), "у карты есть кнопки")

    print("\n— Контент кликабелен —")
    ctx = Ctx(store)
    for tab in ("mobs", "items", "npcs", "classes"):
        ctx.state["content_tab"] = tab
        html = page_content.render(ctx)
        check("data-act=" in html and "clickable" in html, f"вкладка {tab}: строки кликабельны")
    check("mf_name" in page_content.mob_form(ctx, 0), "форма моба открывается")
    check("if_name" in page_content.item_form(ctx, 0), "форма предмета открывается")
    check("nf_name" in page_content.npc_form(ctx, 0), "форма NPC открывается")
    check("cf_title" in page_content.class_form(ctx, "mage"), "форма класса открывается")

    ca.dom = FakeDom
    FakeDom.vals = {"#mf_name": "Лютый ворг", "#mf_desc": "тест", "#mf_level": "9",
                    "#mf_hp": "120", "#mf_dmg": "17", "#mf_def": "6",
                    "#mf_gold": "44", "#mf_exp": "88", "#mf_loc": "1"}
    ca._mob_save(ctx, "0")
    check(data.MOBS[0][0] == "Лютый ворг", "правка моба сохраняется")
    n = len(data.MOBS)
    ca._mob_save(ctx, "new")
    check(len(data.MOBS) == n + 1, "новый моб добавляется")
    data.MOBS[0] = ("сброс", "", 1, 1, 1, 1, 1, 1, 0)
    ca.restore(store)
    check(data.MOBS[0][0] == "Лютый ворг", "контент переживает перезагрузку панели")

    print("\n— Карта порталов —")
    ctx.state["world_tab"] = "dungeons"
    html = page_dungeons.render(ctx)
    check("Карта порталов" in html, "в разделе подземелий есть карта")
    tpl = store.settings["dungeon_templates"][0]
    key = next(k for k, c in store.world.items() if c.loc == 0 and c.passable and not c.link)
    tpl["portal_cell"] = key
    html = page_dungeons.render(ctx)
    check(html.count("data-act='dungeon-focus'") == 1, "открытый портал отмечен на карте")
    check("dungeon-close" in page_dungeons.dungeon_form(ctx, tpl), "карточка портала кликабельна")

    print("\n— Адрес панели для кнопки в боте —")
    check(permissions.normalize_url("my.host/") == "https://my.host", "схема https добавляется")
    check(permissions.normalize_url("http://a.b/p/") == "http://a.b/p", "хвостовой слэш убран")
    check(permissions.normalize_url("  ") == "", "пустой адрес остаётся пустым")
    check(permissions.login_url("my.host", 7) == "https://my.host/admin-login?uid=7",
          "ссылка входа собирается")
    check(permissions.login_url("", 7) == "", "без адреса ссылки нет")

    store.settings["panel_url"] = ""
    labels = [b[0] for row in game.handle(p, "admin").keyboard for b in row]
    check(not any("Открыть панель" in t for t in labels), "без адреса кнопки панели нет")

    store.settings["panel_url"] = "https://my-game.onrender.com"
    kb = game.handle(p, "admin").keyboard
    labels = [b[0] for row in kb for b in row]
    check(any("Открыть панель" in t for t in labels), "с адресом кнопка появилась")
    url_btns = [b[1] for row in kb for b in row if isinstance(b[1], dict)]
    check(url_btns and url_btns[0]["url"].endswith(f"/admin-login?uid={p.tg_id}"),
          "кнопка ведёт на вход с логином игрока")

    from webapp.telegram import TelegramBot
    built = [TelegramBot._button(t, d) for row in kb for t, d in row]
    check(any("url" in b for b in built), "url-кнопка уходит в Telegram как ссылка")
    check(all("callback_data" in b or "url" in b for b in built),
          "остальные кнопки остались callback-ами")

    print("\n— Туман войны —")
    q = store.player(777, "Новичок")
    Game(store).handle(q, "make:rogue")
    check(mapview.is_visited(q, 0, q.x, q.y), "стартовая клетка открыта")
    check(not mapview.is_visited(q, 0, 0, 0), "дальний угол ещё скрыт")

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
