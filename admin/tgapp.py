"""Вход в админ-панель через Telegram Mini App — без пароля.

Кнопка «🌐 Открыть панель» в боте открывает /tgapp как мини-приложение.
Страница забирает у Telegram подписанный initData и шлёт его на
/tgapp/auth; сервер проверяет HMAC-подпись токеном бота (подделать её без
токена нельзя), сверяет, что пользователю выдан доступ веб-админа, и ставит
обычную сессионную cookie панели.

Классический вход /admin-login (Telegram ID + пароль) остаётся запасным
путём — например, для обычного браузера на компьютере.
"""
import hashlib
import hmac
import json
import logging
import os
import time
from urllib.parse import parse_qsl

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select

from core.database import async_session
from core.models import AppSetting, User
from admin import auth as webauth

logger = logging.getLogger("tgapp")

router = APIRouter()

MAX_AUTH_AGE = 24 * 3600  # подписанные данные принимаем в течение суток

PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Shadow Lands — вход в панель</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  body { margin: 0; min-height: 100vh; display: flex; align-items: center;
         justify-content: center; background: #14161c; color: #e8e6df;
         font: 16px/1.5 system-ui, sans-serif; text-align: center; }
  #status { padding: 2em; max-width: 26em; }
  a { color: #8ab4ff; }
</style>
</head>
<body>
<div id="status">⏳ Проверяем доступ…</div>
<script>
const tg = window.Telegram && window.Telegram.WebApp;
const status = document.getElementById('status');

async function main() {
  const initData = tg && tg.initData;
  if (!initData) {
    status.innerHTML =
      'Этот вход работает внутри Telegram.<br><br>' +
      'Открой панель кнопкой «🌐 Открыть панель» в боте — ' +
      'или войди <a href="/admin-login">по логину и паролю</a>.';
    return;
  }
  tg.ready();
  tg.expand();
  try {
    const resp = await fetch('/tgapp/auth', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({initData: initData})
    });
    const data = await resp.json();
    if (data.ok) {
      status.textContent = '✅ Готово, открываю панель…';
      window.location.href = '/';
    } else {
      status.textContent = '⛔ ' + (data.error || 'Доступ запрещён.');
    }
  } catch (e) {
    status.textContent = '⚠️ Ошибка соединения. Попробуй ещё раз.';
  }
}
main();
</script>
</body>
</html>
"""


async def _bot_token() -> str:
    """Токен бота из настроек панели (его же использует bot_runner), env — запасной."""
    try:
        async with async_session() as session:
            result = await session.execute(
                select(AppSetting).where(AppSetting.key == "bot_token")
            )
            setting = result.scalar_one_or_none()
        if setting and setting.value and setting.value.strip():
            return setting.value.strip()
    except Exception:
        pass
    return os.getenv("BOT_TOKEN", "")


def validate_init_data(init_data: str, bot_token: str, now: int | None = None):
    """Разобрать и проверить Telegram WebApp initData.

    Возвращает dict полей ('user' уже как dict) или None. Алгоритм из
    документации Telegram Mini Apps: secret_key = HMAC_SHA256("WebAppData",
    bot_token), отпечаток = HMAC_SHA256(secret_key, data_check_string), где
    data_check_string — все поля кроме hash, отсортированные по ключу,
    склеенные '\\n'. Тот же подход использует aiogram (поле signature при
    этом остаётся частью строки — исключается только hash).
    """
    if not init_data or not bot_token:
        return None
    try:
        pairs = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None
    got_hash = pairs.pop("hash", "")
    if not got_hash:
        return None
    data_check = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expect = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, got_hash):
        return None

    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        return None
    now = int(time.time()) if now is None else now
    if auth_date <= 0 or now - auth_date > MAX_AUTH_AGE:
        return None

    user_raw = pairs.get("user")
    if not user_raw:
        return None
    try:
        user = json.loads(user_raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(user, dict) or not isinstance(user.get("id"), int):
        return None
    pairs["user"] = user
    return pairs


@router.get("/tgapp", response_class=HTMLResponse)
async def tgapp_page():
    return HTMLResponse(PAGE)


@router.post("/tgapp/auth")
async def tgapp_auth(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    data = validate_init_data(str(payload.get("initData", "") or ""),
                              await _bot_token())
    if not data:
        return JSONResponse(
            {"ok": False,
             "error": "Подпись Telegram не сошлась. Открой панель заново "
                      "кнопкой из бота."},
            status_code=403,
        )

    tg_user = data["user"]
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == tg_user["id"])
        )
        user = result.scalar_one_or_none()

    if not user or not user.is_web_admin:
        return JSONResponse(
            {"ok": False,
             "error": "Этому Telegram-пользователю доступ в панель не выдан."},
            status_code=403,
        )

    token = webauth.make_session_token(user.id, user.web_admin_role or "viewer")
    resp = JSONResponse({"ok": True})
    resp.set_cookie(
        webauth.COOKIE_NAME, token,
        max_age=webauth.SESSION_MAX_AGE, httponly=True, samesite="lax",
    )
    logger.info(f"Mini App вход: {tg_user['id']} ({user.web_admin_role or 'viewer'})")
    return resp
