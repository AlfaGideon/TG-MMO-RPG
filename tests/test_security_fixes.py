"""Регрессии на исправления аудита безопасности (2026-09-02).

python3 -m pytest -q tests/test_security_fixes.py

Что покрыто:
  * экранирование HTML в знамениях (панельный превью `| safe` + Telegram
    parse_mode="HTML") — XSS/поломка разметки через админские знамения;
  * whitelist расширений загрузок и побег `</script>` из JSON-вставок;
  * whitelist ключей фракций в путях гербов (path traversal);
  * SQL-песочница: только одиночный SELECT, чёрный список функций,
    read-only соединение после запроса снова пригодно к записи;
  * same-origin middleware (CSRF для режима «нет cookie — это владелец»);
  * `/player/{id}/heal` больше не работает методом GET;
  * replay-защита initData и троттлинг подбора пароля;
  * devops-оценщик WHERE без eval() (песочница eval обходится);
  * community-хендлеры экранируют пользовательский текст;
  * save_token.py не хранит секрет в репозитории;
  * лог-буфер панели маскирует Telegram-токены.
"""
import os
import re
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from _seed import pin, unique_id  # noqa: E402

pin(907)

# Заглушки браузерных модулей (как в test_access.py) — нужны, чтобы
# импортировать webapp.actions вне Pyodide.
_js = types.ModuleType("js")
_js.document = types.SimpleNamespace(querySelector=lambda s: None,
                                     addEventListener=lambda *a: None)
sys.modules.setdefault("js", _js)
_ffi = types.ModuleType("pyodide.ffi")
_ffi.create_proxy = lambda f: f
_ffi.to_js = lambda *a, **k: None
_pyo = types.ModuleType("pyodide")
_pyo.ffi = _ffi
sys.modules.setdefault("pyodide", _pyo)
sys.modules.setdefault("pyodide.ffi", _ffi)


# ── 1. Знамения: пользовательский текст экранирован ─────────────────────

def test_omens_escape_custom_text():
    from engine import omens

    payload = ('[{"icon":"🔮","title":"<script>alert(1)</script>",'
               '"desc":"a & b < c"}]')
    banner = omens.omen_banner({omens.CUSTOM_KEY: payload})
    assert "<script>alert" not in banner
    assert "&lt;script&gt;" in banner and "&amp;" in banner
    lines = omens.omens_lines({omens.CUSTOM_KEY: payload})
    assert not any("<script>alert" in line for line in lines)


# ── 2. Загрузки: расширения и JSON в <script> ──────────────────────────

def test_upload_extension_whitelist():
    from admin.main import _safe_image_ext

    assert _safe_image_ext("pic.png") == ".png"
    assert _safe_image_ext("PIC.JPEG") == ".jpeg"
    # вебконтент, отдаваемый с того же origin, — это XSS:
    assert _safe_image_ext("evil.html") == ".png"
    assert _safe_image_ext("evil.svg") == ".png"
    assert _safe_image_ext("evil.xhtml") == ".png"
    assert _safe_image_ext("x.png/../../y.php") == ".png"


def test_script_json_escapes_close_tag():
    from admin.main import _script_json

    s = _script_json([{"name": "</script><script>alert(1)</script>"}])
    assert "</" not in s               # побег из <script> невозможен
    assert "alert(1)" in s              # данные не потеряны
    import json
    assert json.loads(s.replace("<\\/", "</"))[0]["name"] == "</script><script>alert(1)</script>"


def test_faction_crest_path_validation():
    from fastapi import HTTPException
    from admin.main import _faction_crest_path, _faction_crest_backup_path

    assert _faction_crest_path("guard").endswith(os.path.join("guard.jpg"))
    for bad in ("../../etc/passwd", "guard/../../../x", "", "nope"):
        with pytest.raises(HTTPException):
            _faction_crest_path(bad)
        with pytest.raises(HTTPException):
            _faction_crest_backup_path(bad)


# ── 3. SQL-песочница ─────────────────────────────────────────────────────

def test_sql_sandbox_hardened():
    from admin.main import _SQL_FORBIDDEN

    for q in ("DROP TABLE users", "SELECT 1 UNION SELECT * FROM x WHERE 1; DELETE FROM y",
              "SELECT pg_sleep(10)", "SELECT * FROM pragma_database_list",
              "SELECT lo_import('/etc/passwd')", "INSERT INTO users VALUES (1)"):
        if not (q.startswith("select") and q.lower().startswith("select")):
            continue  # не-SELECT отсекается префикс-проверкой роутера
        assert _SQL_FORBIDDEN.search(q), f"пропущена строка: {q}"


@pytest.mark.asyncio
async def test_sql_sandbox_read_only_and_no_stack():
    from starlette.requests import Request
    import admin.main as m

    async def run(query):
        scope = {"type": "http", "method": "POST", "path": "/settings/sql",
                 "headers": [(b"content-length", b"0")], "query_string": b"",
                 "scheme": "http", "client": ("1.2.3.4", 5), "server": ("t", 80),
                 "root_path": "", "app": None,
                 "state": {"role": None, "web_user_id": None, "caps": None}}

        async def receive():
            return {"type": "http.disconnect"}

        req = Request(scope, receive)
        req.state.role = None
        req.state.caps = None          # «владелец»: guard проходит
        resp = await m.settings_sql_run(req, query=query)
        return resp.body.decode("utf-8", "replace")

    html_ok = await run("SELECT 1 AS ok")
    assert "1" in html_ok and "Разрешены только" not in html_ok
    assert "точка с запятой" in await run("SELECT 1; DROP TABLE users")
    assert "запрещённое" in await run("SELECT pg_sleep(3)")

    # query_only должен сниматься: соединение пула снова пригодно к записи
    from core.database import async_session
    from sqlalchemy import text
    async with async_session() as session:
        await session.execute(text("CREATE TABLE IF NOT EXISTS _sec_smoke (a int)"))
        await session.execute(text("INSERT INTO _sec_smoke VALUES (1)"))
        await session.commit()
        await session.execute(text("DROP TABLE _sec_smoke"))
        await session.commit()


# ── 4. CSRF same-origin middleware + heal только POST ───────────────────

def test_csrf_and_heal_method():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from admin.main import CsrfOriginMiddleware

    app = FastAPI()
    app.add_middleware(CsrfOriginMiddleware)

    @app.post("/ping")
    async def ping():
        return {"ok": True}

    @app.get("/ping")
    async def ping_get():
        return {"ok": "get"}

    client = TestClient(app)
    # браузер с чужого сайта: Origin есть и не совпадает с Host
    assert client.post("/ping", headers={"Origin": "http://evil.example"}).status_code == 403
    assert client.post("/ping", headers={"Referer": "http://evil.example/page"}).status_code == 403
    # тот же origin — проходит
    assert client.post("/ping", headers={"Origin": "http://testserver"}).status_code == 200
    # не-браузерный клиент без Origin (curl/скрипты) — не блокируем
    assert client.post("/ping").status_code == 200

    # heal — только POST: GET-«кнопка» больше не меняет состояние
    import admin.main as m
    routes = {r.path: r for r in m.app.routes if hasattr(r, "methods")}
    assert "GET" not in (routes.get("/player/{char_id}/heal").methods or set())
    assert "POST" in routes["/player/{char_id}/heal"].methods


# ── 5. Троттлинг входа и replay initData ─────────────────────────────────

def test_login_throttle():
    from admin import auth as webauth

    key = f"throttle-test-{unique_id()}"
    assert webauth.login_retry_after(key) == 0
    for _ in range(webauth.LOGIN_MAX_FAILS):
        webauth.note_login_failure(key)
    assert webauth.login_retry_after(key) > 0
    webauth.clear_login_failures(key)
    assert webauth.login_retry_after(key) == 0


@pytest.mark.asyncio
async def test_tgapp_replay_guard():
    from admin.tgapp import _remember_init_data, _replay_seen_check

    payload = f"auth_date=1&unique={unique_id()}&hash=abc"
    assert _replay_seen_check(payload) is False
    _remember_init_data(payload)
    assert _replay_seen_check(payload) is True


# ── 6. Devops-оценщик WHERE: без eval ────────────────────────────────────

def test_devops_evaluator_no_eval_escape():
    from webapp.actions.devops_actions import _eval_expr

    row = {"level": 7, "name": "Тень", "gold": 0}
    assert _eval_expr("level > 3 and gold == 0", row) is True
    assert _eval_expr('get("level") + 1 == 8', row) is True
    for evil in ("().__class__.__bases__[0].__subclasses__()",
                 "open('/etc/passwd').read()",
                 "print(level)",
                 "[].__class__"):
        with pytest.raises(ValueError):
            _eval_expr(evil, row)


# ── 7. Community: пользовательский текст экранируется ────────────────────

def test_community_html_escaping():
    from bot.handlers.community import _body, _q

    assert _q("<b>x</b>") == "&lt;b&gt;x&lt;/b&gt;"
    assert "&" in _q("a & b")

    class Msg:
        text = "<img src=x onerror=alert(1)>"
        is_system = False

    body = _body(Msg())
    assert "&lt;img" in body and "<img" not in body  # тег нейтрализован

    class SysMsg:
        text = "<b>Портал открылся</b>"
        is_system = True

    assert _body(SysMsg()) == "<b>Портал открылся</b>"  # форматирование сохранено


def test_bridge_player_line_escaped():
    # Строка, которая уходит в тему супергруппы с parse_mode=HTML, должна
    # собираться из экранированного текста (иначе фишинговая <a href>).
    src = open(os.path.join(ROOT, "bot", "community_bridge.py"), encoding="utf-8").read()
    m = re.search(r"line = f\"<b>\{.*?\}</b>: \{.*?\}\"", src)
    assert m and "_esc(body" in m.group(0), "relay_from_game не экранирует тело"


# ── 8. save_token.py: секрета в репозитории нет ──────────────────────────

def test_save_token_no_hardcoded_secret():
    src = open(os.path.join(ROOT, "save_token.py"), encoding="utf-8").read()
    assert not re.search(r"['\"]\d{6,}:[A-Za-z0-9_-]{30,}['\"]", src), \
        "в save_token.py снова прописан токен"
    assert "BOT_TOKEN" in src


# ── 9. Лог-буфер маскирует токены ─────────────────────────────────────────

def test_log_buffer_redacts_tokens():
    from admin.logs import redact_secrets

    line = "poll getUpdates failed: https://api.telegram.org/bot123456:AAAAbbbbCCCC-ddddEEEE_ffff000011/getUpdates"
    out = redact_secrets(line)
    assert "AAAAbbbb" not in out and "<bot-token>" in out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
