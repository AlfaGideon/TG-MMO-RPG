"""Telegram Mini App для админ-панели: подпись initData, вход по кнопке,
автовыбор бинаря cloudflared и URL-хелперы.

python3 tests/test_miniapp.py
"""
import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
from unittest import mock
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Временная БД ДО импорта core.* — модуль читает DATABASE_URL при загрузке.
_TMP = tempfile.mkdtemp(prefix="tgmmorpg_miniapp_")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{os.path.join(_TMP, 'miniapp.db')}"

try:
    from sqlalchemy import select
    from admin.tgapp import validate_init_data, router as tgapp_router
    from admin import auth as webauth
    from core import tunnel as tunnel_mod
    from core.database import async_session, init_db
    from core.models import AppSetting, User
    from core.settings_store import build_login_url, build_miniapp_url, platform_public_url
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ImportError as e:
    print(f"⚠ Пропуск: нет зависимостей серверного стека ({e})")
    sys.exit(0)

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


# ── подпись initData ────────────────────────────────────────

TOKEN = "123456:ABC-DEF-test-token"


def make_init_data(fields: dict, token: str = TOKEN, sign: bool = True) -> str:
    """Собрать initData с подписью так, как это делает Telegram."""
    fields = dict(fields)
    got_hash = fields.pop("hash", None)
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    if sign:
        secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        got_hash = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if got_hash:
        fields["hash"] = got_hash
    return urlencode(fields)


def base_fields(auth_date=None):
    return {
        "auth_date": str(auth_date or int(time.time())),
        "chat_instance": "-9009",
        "chat_type": "private",
        "user": json.dumps({"id": 555001, "first_name": "Хозяин",
                            "language_code": "ru"}, ensure_ascii=False),
        "signature": "fake-ed25519-signature",  # поле входит в проверку hash
    }


def test_validate():
    print("— Подпись initData —")
    good = make_init_data(base_fields())
    data = validate_init_data(good, TOKEN)
    check(data is not None and data["user"]["id"] == 555001,
          "корректная подпись проходит (в т.ч. с полем signature)")

    check(validate_init_data(good, "999:WRONG") is None,
          "чужой токен не проходит")

    tampered = good.replace("555001", "999999", 1)
    check(validate_init_data(tampered, TOKEN) is None,
          "подмена id ломает подпись")

    old = make_init_data(base_fields(auth_date=int(time.time()) - 25 * 3600))
    check(validate_init_data(old, TOKEN) is None,
          "auth_date старше суток отклоняется")

    fresh = make_init_data(base_fields(auth_date=int(time.time()) - 60))
    check(validate_init_data(fresh, TOKEN) is not None,
          "свежий auth_date принимается")

    no_hash = make_init_data(base_fields(), sign=False)
    check(validate_init_data(no_hash, TOKEN) is None,
          "без hash не проходит")

    bad_user = make_init_data({**base_fields(), "user": "not-json"})
    check(validate_init_data(bad_user, TOKEN) is None,
          "битый user json не проходит")

    no_user = make_init_data({k: v for k, v in base_fields().items() if k != "user"})
    check(validate_init_data(no_user, TOKEN) is None,
          "без user не проходит")

    check(validate_init_data("", TOKEN) is None, "пустые initData отклоняются")
    check(validate_init_data(good, "") is None, "без токена бота проверка не работает")


# ── вход через эндпоинт ─────────────────────────────────────

def test_auth_endpoint():
    print("— Эндпоинт /tgapp/auth —")
    import asyncio

    async def seed():
        await init_db()
        async with async_session() as s:
            s.add(AppSetting(key="bot_token", value=TOKEN))
            admin = User(telegram_id=555001, first_name="Хозяин",
                         is_web_admin=True, web_admin_role="viewer")
            player = User(telegram_id=555777, first_name="Игрок")
            s.add_all([admin, player])
            await s.commit()

    asyncio.run(seed())

    app = FastAPI()
    app.include_router(tgapp_router)
    client = TestClient(app)

    resp = client.get("/tgapp")
    check(resp.status_code == 200 and "telegram-web-app.js" in resp.text,
          "страница Mini App отдаётся и тянет telegram-web-app.js")

    uid = 555001
    good = make_init_data(base_fields())
    resp = client.post("/tgapp/auth", json={"initData": good})
    check(resp.status_code == 200 and resp.json().get("ok"),
          "веб-админ входит без пароля")
    cookie = client.cookies.get(webauth.COOKIE_NAME)
    check(bool(cookie) and webauth.parse_session_token(cookie) is not None,
          "ставится валидная сессионная cookie панели")

    other = make_init_data({**base_fields(),
                            "user": json.dumps({"id": 555777,
                                                "first_name": "Игрок"},
                                               ensure_ascii=False)})
    resp = client.post("/tgapp/auth", json={"initData": other})
    check(resp.status_code == 403 and not resp.json().get("ok"),
          "обычному игроку вход запрещён")

    resp = client.post("/tgapp/auth", json={"initData": "garbage"})
    check(resp.status_code == 403, "мусор вместо initData — 403")

    unknown = make_init_data({**base_fields(),
                              "user": json.dumps({"id": 424242,
                                                  "first_name": "Призрак"},
                                                 ensure_ascii=False)})
    resp = client.post("/tgapp/auth", json={"initData": unknown})
    check(resp.status_code == 403, "подпись валидна, но такого пользователя нет — 403")


# ── туннель и URL-хелперы ───────────────────────────────────

def test_tunnel_helpers():
    print("— Quick Tunnel: выбор бинаря и проверка адресов —")

    def bin_for(system, machine):
        with mock.patch.object(tunnel_mod.platform, "system", return_value=system), \
             mock.patch.object(tunnel_mod.platform, "machine", return_value=machine):
            return tunnel_mod.binary_url()

    url, name = bin_for("Windows", "AMD64")
    check(url.endswith("cloudflared-windows-amd64.exe") and name == "cloudflared.exe",
          "Windows amd64 — правильный релиз")
    url, name = bin_for("Linux", "x86_64")
    check(url.endswith("cloudflared-linux-amd64") and name == "cloudflared",
          "Linux amd64 — правильный релиз")
    url, name = bin_for("Linux", "aarch64")
    check(url.endswith("cloudflared-linux-arm64"), "Linux arm64 — правильный релиз")
    url, name = bin_for("Darwin", "arm64")
    check(url.endswith("cloudflared-darwin-arm64.tgz"), "macOS arm64 — tgz-архив")
    check(bin_for("Linux", "riscv64") == ("", ""), "неизвестная архитектура — без скачивания")

    # Проверяем, что trycloudflare.com адреса распознаются как временные
    check(tunnel_mod.is_quick_tunnel_url("https://example.trycloudflare.com"),
          "trycloudflare.com адрес распознаётся как временный")
    check(not tunnel_mod.is_quick_tunnel_url("https://panel.example.com"),
          "обычный ручной домен не считается временным")

    # Туннель отключён
    check(not tunnel_mod.tunnel_enabled(), "туннель отключён по умолчанию")

    hosted_env = {**env, "RENDER_EXTERNAL_URL": "https://shadow-lands.onrender.com/"}
    with mock.patch.dict(os.environ, hosted_env, clear=True):
        check(platform_public_url() == "https://shadow-lands.onrender.com",
              "Render URL выбирается вместо временного Quick Tunnel")
    replit_env = {**env, "REPLIT_DOMAINS": "game.replit.app,alias.replit.app"}
    with mock.patch.dict(os.environ, replit_env, clear=True):
        check(platform_public_url() == "https://game.replit.app",
              "первый домен Replit выбирается для Mini App")


OLD = "https://old-tunnel.trycloudflare.com"
NEW = "https://new-tunnel.trycloudflare.com"


def test_stale_tunnel_url_is_never_served():
    """Главная регрессия: после перезапуска бот НЕ отдаёт старую ссылку.

    Симптом из жизни: сервер перезапускали целиком, а игрокам/админам
    одноразовый, и старый адрес отвечает страницей Cloudflare 1033.
    """
    print("— Устаревший адрес Quick Tunnel не выдаётся —")
    import asyncio

    from core import settings_store as st


    async def scenario():
        results = {}
        # Состояние прошлого запуска: адрес лежит в БД.
        await st.set_setting(st.PANEL_URL_KEY, OLD)
        st.set_active_tunnel_url("")
        st.mark_tunnel_managed(True)

        # Пока новый туннель не поднялся, старый адрес отдавать нельзя.
        results["hidden"] = await st.get_panel_url()
        # …и он же должен быть вычищен из настроек, а не остаться ждать.
        results["wiped"] = await st.get_setting(st.PANEL_URL_KEY)

        # Туннель поднялся — отдаём свежий адрес.
        st.set_active_tunnel_url(NEW)
        await st.set_panel_url(NEW)
        results["fresh"] = await st.get_panel_url()

        # Ручной домен (VPS/Render) сохранённым остаётся всегда.
        st.set_active_tunnel_url("")
        st.mark_tunnel_managed(True)
        await st.set_panel_url("https://panel.example.com")
        results["manual"] = await st.get_panel_url()

        # ADMIN_TUNNEL=0: туннелем правит кто-то снаружи — не трогаем адрес.
        st.mark_tunnel_managed(False)
        await st.set_panel_url(OLD)
        results["external"] = await st.get_panel_url()
        st.mark_tunnel_managed(False)
        st.set_active_tunnel_url("")
        return results

    r = asyncio.run(scenario())
    check(r["hidden"] == "", "старый адрес туннеля не отдаётся боту")
    check(r["wiped"] == "", "старый адрес удаляется из настроек")
    check(r["fresh"] == NEW, "новый адрес туннеля отдаётся сразу")
    check(r["manual"] == "https://panel.example.com",
          "ручной домен не считается устаревшим туннелем")
    check(r["external"] == OLD,
          "при ADMIN_TUNNEL=0 чужой туннель не сбрасывается")

    check(st.is_temporary_tunnel_url(OLD), "адрес Quick Tunnel распознаётся")
    check(not st.is_temporary_tunnel_url("https://panel.example.com"),
          "обычный домен не считается временным")


def test_tunnel_verification():
    """Адрес публикуется только после ответа /health с нашей меткой."""
    print("— Проверка живости адреса перед публикацией —")
    import asyncio

    from core.settings_store import INSTANCE_ID

    class FakeResponse:
        def __init__(self, body):
            self._body = body.encode()

        def read(self, _n=None):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def ours(*_a, **_kw):
        return FakeResponse(json.dumps({"status": "ok", "instance": INSTANCE_ID}))

    def stranger(*_a, **_kw):
        return FakeResponse(json.dumps({"status": "ok", "instance": "other"}))

    def dead(*_a, **_kw):
        raise OSError("Cloudflare 1033")

    with mock.patch.object(tunnel_mod.urllib.request, "urlopen", ours):
        ok = asyncio.run(tunnel_mod.verify_tunnel_url(
    check(ok, "адрес нашего процесса подтверждается")

    with mock.patch.object(tunnel_mod.urllib.request, "urlopen", stranger):
        ok = asyncio.run(tunnel_mod.verify_tunnel_url(
    check(not ok, "чужой сервер на том же домене не принимается")

    with mock.patch.object(tunnel_mod.urllib.request, "urlopen", dead):
        ok = asyncio.run(tunnel_mod.verify_tunnel_url(
    check(not ok, "мёртвый адрес (1033) не подтверждается")


def test_url_helpers():
    print("— URL-адреса для кнопок —")
    check(build_miniapp_url("https://panel.example.com/", 42) ==
          "https://panel.example.com/tgapp?uid=42",
          "miniapp-ссылка ведёт на /tgapp и обрезает слэш")
    check(build_miniapp_url("panel.example.com", 42).startswith("https://"),
          "адрес без схемы дополняется https://")
    check(build_login_url("https://panel.example.com", 42) ==
          "https://panel.example.com/admin-login?uid=42",
          "классическая ссылка всё ещё на /admin-login")
    check(build_miniapp_url("", 42) == "", "без адреса панели miniapp-ссылки нет")


def main():
    test_validate()
    test_auth_endpoint()
    test_tunnel_helpers()
    test_stale_tunnel_url_is_never_served()
    test_tunnel_verification()
    test_url_helpers()

    print()
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}:")
        for f in FAILED:
            print("   -", f)
        return 1
    print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
