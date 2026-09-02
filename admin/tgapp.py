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

# Защита от повтора (replay): initData — «bearer»-данные, их можно передать
# дважды (скрипт, повторная отправка после XSS). Подпись не различает
# «первый» и «второй» вход, поэтому короткое время храним отпечатки
# УСПЕШНО принятых initData и второй такой же запрос без живой сессии
# отклоняем. Живая сессия — послабление намеренное: при перезагрузке
# мини-приложения Telegram отдаёт тот же initData, блокировать честный вход
# нельзя; при следующем открытии кнопки initData будет свежий.
_REPLAY_TTL = 120
_replay_seen: "dict[str, float]" = {}


def _replay_fingerprint(init_data: str) -> str:
    return hashlib.sha256(init_data.encode("utf-8", "replace")).hexdigest()


def _replay_seen_check(init_data: str) -> bool:
    """True — такие initData успешно принимали минуту назад."""
    now = time.time()
    if len(_replay_seen) > 4096:
        for key in [k for k, t in _replay_seen.items() if now - t > _REPLAY_TTL]:
            _replay_seen.pop(key, None)
    return now - _replay_seen.get(_replay_fingerprint(init_data), 0.0) < _REPLAY_TTL


def _remember_init_data(init_data: str) -> None:
    _replay_seen[_replay_fingerprint(init_data)] = time.time()


async def _has_live_session(request: Request) -> bool:
    """Есть ли у клиента уже проверенная живая сессия веб-админа."""
    existing = webauth.parse_session_token(request.cookies.get(webauth.COOKIE_NAME, ""))
    if not existing:
        return False
    try:
        async with async_session() as session:
            fresh_user = await session.get(User, existing[0])
    except Exception:
        return False
    return bool(fresh_user is not None and fresh_user.is_web_admin)

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
    if auth_date <= 0 or now - auth_date > MAX_AUTH_AGE or auth_date > now + 300:
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
    init_data = str(payload.get("initData", "") or "")

    # Повторно присланный initData (перезагрузка мини-приложения Telegram
    # отдаёт ту же строку) — пропускаем только клиентам с живой сессией;
    # чужая «найдённая» подпись без cookie второй раз не сработает.
    if _replay_seen_check(init_data) and not await _has_live_session(request):
        return JSONResponse(
            {"ok": False,
             "error": "Эти данные входа уже использованы минуту назад. "
                      "Закрой и снова открой панель кнопкой из бота."},
            status_code=403,
        )
    data = validate_init_data(init_data, await _bot_token())
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

    _remember_init_data(init_data)
    token = webauth.make_session_token(user.id, user.web_admin_role or "viewer")
    resp = JSONResponse({"ok": True})
    proto = (request.headers.get("x-forwarded-proto", "") or request.url.scheme)
    resp.set_cookie(
        webauth.COOKIE_NAME, token,
        max_age=webauth.SESSION_MAX_AGE, httponly=True, samesite="lax",
        secure=proto.split(",")[0].strip().lower() == "https",
    )
    logger.info(f"Mini App вход: {tg_user['id']} ({user.web_admin_role or 'viewer'})")
    return resp
