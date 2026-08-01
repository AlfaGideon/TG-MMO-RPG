"""Прокси для бота (Tor / SOCKS5): валидация, диагностика, понятные ошибки.

Прокси используется ТОЛЬКО ботом (aiogram) для связи с Telegram.
Админ-панель ходит напрямую — открывай её в обычном Chrome/Edge, не через Tor.

Типовые адреса:
  socks5://127.0.0.1:9050  — системный сервис Tor
  socks5://127.0.0.1:9150  — Tor Browser
Пустое значение = прямое подключение.

Модуль намеренно не импортирует aiogram/aiohttp/aiohttp-socks на верхнем
уровне: валидация и подсказки должны работать даже там, где эти пакеты
не установлены (это и есть один из диагностируемых случаев).
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Схемы, которые понимает aiohttp-socks (через aiogram.AiohttpSession).
ALLOWED_SCHEMES = ("socks4", "socks5", "socks5h", "http", "https")
INSTALL_HINT = "pip install aiohttp-socks"

TCP_PROBE_TIMEOUT = 4.0   # сек: проверка, что прокси вообще слушает порт
TG_PROBE_TIMEOUT = 10.0   # сек: проверка связи с Telegram через прокси
TG_PROBE_URL = "https://api.telegram.org/"

# Вид: scheme://[user:pass@]host[:port]  (IPv6 — в квадратных скобках).
_URL_RE = re.compile(
    r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]*)://"
    r"(?:(?P<userinfo>[^/@]+)@)?"
    r"(?P<host>\[[^\]]+\]|[^/:@]+)"
    r"(?::(?P<port>\d+))?"
    r"(?P<rest>.*)$"
)


def is_installed() -> bool:
    """Установлен ли пакет aiohttp-socks (без него aiogram не ходит через SOCKS)."""
    return importlib.util.find_spec("aiohttp_socks") is not None


def validate_proxy_url(url: str) -> Optional[str]:
    """Проверяет адрес прокси. Возвращает текст ошибки (по-русски) или None.

    None означает «всё в порядке» (включая пустую строку — прямое подключение).
    """
    url = (url or "").strip()
    if not url:
        return None

    m = _URL_RE.match(url)
    if not m:
        return (
            "Некорректный адрес прокси. Ожидается вид socks5://хост:порт, "
            "например socks5://127.0.0.1:9150."
        )

    scheme = m.group("scheme").lower()
    if scheme not in ALLOWED_SCHEMES:
        return (
            f"Схема прокси «{scheme}» не поддерживается. Используйте "
            "socks5://, socks4://, socks5h://, http:// или https://."
        )
    if not m.group("port"):
        return (
            "В адресе прокси не указан порт. Пример: socks5://127.0.0.1:9150 "
            "(Tor Browser) или socks5://127.0.0.1:9050 (системный Tor)."
        )
    port = int(m.group("port"))
    if not 0 < port < 65536:
        return "Порт прокси вне допустимого диапазона (1–65535)."
    if m.group("rest"):
        return "В адресе прокси не должно быть пути или параметров. Пример: socks5://127.0.0.1:9150"
    return None


def parse_proxy_url(url: str) -> Optional[Tuple[str, int]]:
    """(host, port) для TCP-проверки; None, если адрес пустой или битый."""
    m = _URL_RE.match((url or "").strip())
    if not m or not m.group("port"):
        return None
    host = m.group("host")
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    return host, int(m.group("port"))


def _host_port_text(url: str) -> str:
    parsed = parse_proxy_url(url)
    if parsed:
        host, port = parsed
        return f"{host}:{port}"
    return (url or "").strip() or "прокси"


def error_tip(raw_error: str, proxy_url: str = "") -> str:
    """Короткая русская подсказка к сырой ошибке (или пустая строка).

    Используется и в панели, и внутри bot/runner.py, чтобы вместо
    англоязычного исключения aiogram админ видел, что делать.
    """
    low = (raw_error or "").lower()

    # aiogram: RuntimeError, когда aiohttp-socks не установлен
    if "aiohttp-socks" in low or "aiohttp_socks" in low:
        return (
            "Не установлен пакет aiohttp-socks — без него aiogram не умеет "
            f"ходить через SOCKS-прокси. Установите: {INSTALL_HINT}, затем "
            "перезапустите сервер и нажмите «Запустить бота»."
        )
    if not proxy_url:
        return ""

    # Не удалось достучаться до Telegram через прокси
    if (
        "clientconnectorerror" in low
        or "semaphore" in low
        or "таймаут" in low
        or "timed out" in low
        or "timeout" in low
        or "refused" in low
        or "unreachable" in low
        or "couldn't connect" in low
        or "could not connect" in low
        or "cannot connect" in low
        or "connect call failed" in low
        or "connect to proxy" in low
        or "proxyconnectionerror" in low
        or "error connecting" in low
    ):
        where = _host_port_text(proxy_url)
        return (
            f"Похоже, прокси {where} недоступен или не успевает ответить. "
            "Проверьте, что Tor запущен и слушает этот порт (Tor Browser — "
            "9150, системный Tor — 9050), затем нажмите «Запустить бота». "
            "Кнопка «🔌 Проверить» рядом с полем прокси покажет, что именно не так."
        )
    return ""


def friendly_error(raw_error: str, proxy_url: str = "") -> str:
    """Сырая ошибка + понятная подсказка (если удалось распознать)."""
    tip = error_tip(raw_error, proxy_url)
    if not tip:
        return raw_error
    return f"{tip}\nИсходная ошибка: {raw_error}"


def _short(exc: BaseException, limit: int = 180) -> str:
    text = str(exc).strip() or type(exc).__name__
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def probe_tcp(host: str, port: int) -> Tuple[bool, str]:
    """Быстрая проверка: слушает ли прокси свой порт (TCP-коннект)."""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=TCP_PROBE_TIMEOUT
        )
    except Exception as e:
        return (
            False,
            f"Прокси {host}:{port} не отвечает ({_short(e)}). "
            "Проверьте, что Tor запущен и слушает именно этот порт.",
        )
    try:
        writer.close()
        await writer.wait_closed()
    except Exception:
        pass
    return True, f"Прокси {host}:{port} принимает соединения — Tor запущен."


async def probe_telegram(proxy_url: str) -> Tuple[bool, str]:
    """Проверка: достаётся ли api.telegram.org через прокси."""
    try:
        from aiohttp_socks import ProxyConnector
        import aiohttp
    except ImportError:
        return False, f"Не установлен пакет aiohttp-socks. Установите: {INSTALL_HINT}"
    try:
        connector = ProxyConnector.from_url(proxy_url)
        timeout = aiohttp.ClientTimeout(total=TG_PROBE_TIMEOUT)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.get(TG_PROBE_URL, timeout=timeout) as resp:
                await resp.read()  # любой HTTP-статус = соединение через прокси работает
    except Exception as e:
        return (
            False,
            f"Соединение с api.telegram.org через прокси не установлено ({_short(e)}). "
            "Частая причина — Tor ещё не построил цепочку: подождите 10–30 секунд "
            "и нажмите «Проверить» ещё раз.",
        )
    return True, "api.telegram.org доступен через прокси — бот сможет работать."


async def check_proxy(proxy_url: str) -> dict:
    """Пошаговая диагностика прокси для кнопки «🔌 Проверить» в админ-панели.

    Возвращает {"ok": bool, "steps": [{"ok": bool, "text": str}, ...], "error": str|None}.
    Останавливается на первой неудаче, сетевых вызовов дальше не делает.
    """
    url = (proxy_url or "").strip()
    if not url:
        return {
            "ok": False,
            "steps": [{"ok": False, "text": "Прокси не задан — бот подключается напрямую."}],
            "error": "Прокси не задан.",
        }

    err = validate_proxy_url(url)
    if err:
        return {"ok": False, "steps": [{"ok": False, "text": err}], "error": err}
    steps: list[dict] = [{"ok": True, "text": f"Адрес корректен: {url}"}]

    if not is_installed():
        msg = (
            f"Не установлен пакет aiohttp-socks — aiogram не сможет работать "
            f"через прокси. Установите: {INSTALL_HINT}, затем перезапустите сервер."
        )
        steps.append({"ok": False, "text": msg})
        return {"ok": False, "steps": steps, "error": msg}
    steps.append({"ok": True, "text": "Пакет aiohttp-socks установлен — aiogram сможет работать через прокси"})

    parsed = parse_proxy_url(url)
    if parsed is None:  # validate_proxy_url уже пропустил, но страхуемся
        msg = "Не удалось разобрать адрес прокси."
        steps.append({"ok": False, "text": msg})
        return {"ok": False, "steps": steps, "error": msg}
    host, port = parsed
    ok, text = await probe_tcp(host, port)
    steps.append({"ok": ok, "text": text})
    if not ok:
        return {"ok": False, "steps": steps, "error": text}

    ok, text = await probe_telegram(url)
    steps.append({"ok": ok, "text": text})
    if not ok:
        return {"ok": False, "steps": steps, "error": text}

    return {"ok": True, "steps": steps, "error": None}
