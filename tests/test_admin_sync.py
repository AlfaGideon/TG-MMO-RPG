"""Админка в боте + журнал действий + прокладка входа.

python3 tests/test_admin_sync.py
"""
import os
import re
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

from engine import adminbot, adminops, audit, data, permissions  # noqa: E402
from engine.game import Game  # noqa: E402
from engine.storage import Store  # noqa: E402
from webapp.backend import MemoryStorage  # noqa: E402
from webapp.pages import audit as page_audit  # noqa: E402

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


def labels(reply):
    return [b[0] for row in reply.keyboard for b in row]


def setup():
    store = Store(MemoryStorage())
    game = Game(store)
    boss = store.player(100, "Босс")
    game.handle(boss, "make:warrior")
    adminbot.grant(store, boss, "admin")
    victim = store.player(200, "Новичок")
    Game(store).handle(victim, "make:rogue")
    return store, game, boss, victim


def main():
    store, game, boss, victim = setup()

    print("\n— Разделы админки в боте —")
    home = game.handle(boss, "admin")
    for want in ("Сводка", "Игроки", "Порталы", "Рассылка", "Контент", "Журнал"):
        check(any(want in t for t in labels(home)), f"кнопка «{want}» есть у админа")

    print("\n— Права режут разделы —")
    mod = store.player(300, "Модератор")
    Game(store).handle(mod, "make:mage")
    adminbot.grant(store, mod, "moderator")
    mod_home = game.handle(mod, "admin")
    check(any("Игроки" in t for t in labels(mod_home)), "модератор видит игроков")
    check(not any("Рассылка" in t for t in labels(mod_home)),
          "модератор не видит рассылку")
    check(not any("Порталы" in t for t in labels(mod_home)),
          "модератор не видит порталы")
    check(game.handle(mod, "adm:gold:200:100").alert.startswith("Нужно право"),
          "модератору отказано в правке золота")
    check(store.players[200].gold == 50, "золото не изменилось при отказе")

    print("\n— Действия работают из бота —")
    game.handle(boss, "adm:gold:200:250")
    check(store.players[200].gold == 300, "золото начислено")
    game.handle(boss, "adm:lvl:200:2")
    check(store.players[200].level == 3, "уровень поднят")
    before = len(store.players[200].inventory)
    game.handle(boss, "adm:give:200:0")
    check(len(store.players[200].inventory) == before + 1, "предмет выдан")
    store.players[200].hp = 1
    game.handle(boss, "adm:heal:200")
    check(store.players[200].hp > 1, "игрок исцелён")
    game.handle(boss, "adm:tp:200")
    check((store.players[200].loc, store.players[200].x) == (0, 5), "телепорт сработал")

    print("\n— Выдача доступа из бота —")
    game.handle(boss, "adm:rank:200:gamemaster")
    q = store.players[200]
    check(q.is_web_admin and q.web_admin_role == "gamemaster", "ранг выдан из бота")
    check(len(q.web_admin_password) >= 8, "пароль создан")
    check(any("Админка" in t for t in labels(Game(store).handle(q, "menu"))),
          "у игрока появилась кнопка админки")
    game.handle(boss, "adm:revoke:200")
    check(not store.players[200].is_web_admin, "доступ отозван из бота")

    print("\n— Порталы из бота —")
    tpl = adminops.templates(store)[0]
    game.handle(boss, f"adm:popen:{tpl['id']}")
    check(bool(tpl.get("portal_cell")), "портал открыт из бота")
    check(store.world[tpl["portal_cell"]].tile == "cave", "клетка стала порталом")
    game.handle(boss, f"adm:pclose:{tpl['id']}")
    check(not tpl.get("portal_cell"), "портал закрыт из бота")

    print("\n— Журнал общий для бота и панели —")
    entries = audit.entries(store)
    check(len(entries) >= 8, f"записи копятся ({len(entries)})")
    check(all(e["src"] == "bot" for e in entries), "источник помечен как бот")
    check(any("золото" in e["act"].lower() for e in entries), "правка золота в журнале")
    check(entries[0]["ts"] >= entries[-1]["ts"], "новые записи сверху")

    n_bot = audit.count(store, "bot")
    adminops.heal(store, None, 200, source="panel")
    check(audit.count(store, "panel") == 1, "запись из панели отделена")
    check(audit.count(store, "bot") == n_bot, "счётчик бота не сбился")
    check(audit.entries(store)[0]["name"] == audit.OWNER, "владелец подписан")

    seen = game.handle(boss, "adm:audit:0").text
    check("Действия админов" in seen, "журнал открывается в боте")
    check("Босс" in seen or "Владелец" in seen, "в журнале видно автора")

    html = page_audit.render(Ctx(store))
    check("Действия администраторов" in html, "страница журнала рендерится")
    check("🤖 Бот" in html and "🖥 Панель" in html, "видно оба источника")
    check("audit-clear" in html and "audit-src" in html, "кнопки фильтров на месте")

    print("\n— Уведомления игрокам в общей очереди —")
    box = adminops.drain(store)
    check(any(m[0] == 200 for m in box), "игрок получит уведомление")
    check(adminops.drain(store) == [], "очередь очищается после разбора")

    print("\n— Рассылка из бота —")
    r = game.handle(boss, "adm:cast")
    check(store.players[100].pending == "broadcast", "бот ждёт текст рассылки")
    out = game.text_input(boss, "Всем привет!")
    check(out is not None and "очередь" in out.text, "рассылка принята")
    queued = adminops.drain(store)
    check(len(queued) >= 1, "сообщения поставлены в очередь")
    check(all(m[0] != 100 for m in queued), "автор не шлёт письмо сам себе")
    check(store.players[100].pending == "", "режим ожидания снят")
    check(game.text_input(boss, "просто текст") is None, "обычный текст не перехватывается")

    print("\n— Прокладка для GitHub Pages —")
    for name in ("404.html", "admin-login.html", "admin-login/index.html"):
        check(os.path.exists(os.path.join(ROOT, name)), f"{name} существует")
    shim = open(os.path.join(ROOT, "admin-login.html"), encoding="utf-8").read()
    check("uid" in shim and "web_admin_password" in shim, "форма проверяет логин и пароль")
    check("shadowlands_session" in shim, "сессия кладётся в localStorage")
    page404 = open(os.path.join(ROOT, "404.html"), encoding="utf-8").read()
    check("admin-login" in page404, "404 знает про /admin-login")
    check("github.io" in page404, "404 учитывает путь проекта на Pages")

    idx = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    listed = re.findall(r'"([\w/]+\.py)"', idx)
    for mod_name in ("engine/audit.py", "engine/adminops.py", "engine/adminmenu.py",
                     "engine/adminroute.py", "webapp/session.py",
                     "webapp/pages/audit.py", "webapp/actions/audit_actions.py"):
        check(mod_name in listed, f"{mod_name} в манифесте")

    print("\n— Права: полный набор проверок —")
    check(permissions.can(boss, "grant_admin"), "у админа есть выдача доступа")
    try:
        adminops.require(mod, "grant_admin")
        ok = False
    except adminops.Denied:
        ok = True
    check(ok, "adminops поднимает Denied без права")
    check(adminops.require(None, "grant_admin") is True, "владелец проходит без проверки")

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
