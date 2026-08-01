"""Прокси бота (Tor / SOCKS5): валидация адресов, диагностика, понятные ошибки.

Покрывает регрессию, из-за которой панель показывала сырое английское
исключение aiogram («In order to use aiohttp client for proxy requests,
install aiohttp-socks») и непонятный ClientConnectorError с таймаутом:
теперь те же случаи дают русскую подсказку и пошаговую диагностику.

python3 tests/test_proxy.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import proxy as P  # noqa: E402

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


def section(title):
    print(f"\n— {title} —")


# ── валидация адреса ──────────────────────────────────────────

def test_validate_proxy_url():
    section("Валидация адреса прокси")
    cases_ok = [
        "",                                # пусто = прямое подключение
        "socks5://127.0.0.1:9150",         # Tor Browser
        "socks5://127.0.0.1:9050",         # системный Tor
        "socks4://127.0.0.1:1080",
        "socks5h://proxy.example.com:1080",
        "http://127.0.0.1:8118",
        "https://user:pass@proxy.example.com:443",
        "SOCKS5://127.0.0.1:9150",         # регистр схемы не важен
        "socks5://[::1]:9050",             # IPv6
    ]
    for url in cases_ok:
        check(P.validate_proxy_url(url) is None, f"принимает: {url}")

    cases_bad = [
        "socks5://127.0.0.1",              # нет порта
        "ftp://127.0.0.1:21",              # чужая схема
        "127.0.0.1:9150",                  # нет схемы
        "socks5://",                       # пусто
        "socks5://host:99999",             # порт вне диапазона
        "socks5://host:0",
        "socks5://host:9150/extra",        # лишний путь
        "не-адрес",
    ]
    for url in cases_bad:
        check(P.validate_proxy_url(url) is not None, f"отклоняет: {url}")


def test_parse_proxy_url():
    section("Разбор host:port для TCP-проверки")
    check(P.parse_proxy_url("socks5://127.0.0.1:9150") == ("127.0.0.1", 9150),
          "обычный адрес")
    check(P.parse_proxy_url("socks5://user:pass@host.ru:9050") == ("host.ru", 9050),
          "с логином/паролем")
    check(P.parse_proxy_url("socks5://[::1]:9050") == ("::1", 9050),
          "IPv6 без скобок в host")
    check(P.parse_proxy_url("") is None, "пусто → None")
    check(P.parse_proxy_url("socks5://host") is None, "без порта → None")


# ── понятные ошибки ───────────────────────────────────────────

def test_error_tip():
    section("Подсказки к типовым ошибкам")
    aiogram_err = ("In order to use aiohttp client for proxy requests, "
                   "install https://pypi.org/project/aiohttp-socks/")
    tip = P.error_tip(aiogram_err, "socks5://127.0.0.1:9150")
    check("aiohttp-socks" in tip and "pip install" in tip,
          "ошибка про aiohttp-socks → совет по установке")

    connector_err = ("HTTP Client says - ClientConnectorError: Cannot connect to "
                     "host api.telegram.org:443 ssl:default [Превышен таймаут семафора]")
    tip = P.error_tip(connector_err, "socks5://127.0.0.1:9150")
    check("Tor" in tip and "9150" in tip,
          "ClientConnectorError через прокси → совет проверить Tor")

    tip = P.error_tip("ClientConnectorError: [Errno 111] Connection refused",
                      "socks5://127.0.0.1:9050")
    check("Tor" in tip and "9050" in tip, "connection refused → совет проверить Tor")

    # aiohttp-socks 0.9+/0.11: своя формулировка при недоступном прокси
    tip = P.error_tip("[Errno 111] Couldn't connect to proxy 127.0.0.1:9150 "
                      "[Connect call failed ('127.0.0.1', 9150)]",
                      "socks5://127.0.0.1:9150")
    check("Tor" in tip and "9150" in tip,
          "«Couldn't connect to proxy» → совет проверить Tor")

    check(P.error_tip("Some unrelated error", "socks5://127.0.0.1:9150") == "",
          "незнакомая ошибка → без подсказки")
    check(P.error_tip("ClientConnectorError: timeout", "") == "",
          "без прокси подсказка не нужна")
    check(P.error_tip("") == "", "пустая строка → пустая подсказка")


def test_friendly_error_keeps_original():
    section("friendly_error хранит исходную ошибку")
    raw = "HTTP Client says - ClientConnectorError: timeout"
    msg = P.friendly_error(raw, "socks5://127.0.0.1:9150")
    check(raw in msg and "Исходная ошибка" in msg, "подсказка + оригинал")
    check(P.friendly_error("strange", "") == "strange", "без подсказки → как есть")


# ── пошаговая диагностика (без реальной сети) ─────────────────

def test_check_proxy_short_circuits():
    section("Диагностика /api/proxy/check (мок сетевых шагов)")

    async def run():
        # 1. Пустой адрес — сразу ответ, сеть не трогаем
        res = await P.check_proxy("")
        check(not res["ok"] and "напрямую" in res["steps"][0]["text"],
              "пустой адрес → «подключение напрямую»")

        # 2. Битый адрес — ошибка валидации
        res = await P.check_proxy("socks5://host")
        check(not res["ok"] and "порт" in res["error"], "нет порта → ошибка валидации")

        # 3. Нет пакета aiohttp-socks — стоп до сетевых шагов
        orig_installed = P.is_installed
        P.is_installed = lambda: False
        try:
            res = await P.check_proxy("socks5://127.0.0.1:9150")
            check(not res["ok"] and "aiohttp-socks" in res["error"],
                  "нет пакета → понятная ошибка, сеть не проверяется")
            check(len(res["steps"]) == 2, "остановился на шаге про пакет")
        finally:
            P.is_installed = orig_installed

        # 4. Прокси не слушает порт — стоп на TCP-шаге, Telegram не пробуем
        orig_installed = P.is_installed
        orig_tcp, orig_tg = P.probe_tcp, P.probe_telegram
        P.is_installed = lambda: True

        async def no_tcp(host, port):
            return False, f"Прокси {host}:{port} не отвечает"

        async def fail_tg(url):
            raise AssertionError("probe_telegram не должен вызываться")

        P.probe_tcp, P.probe_telegram = no_tcp, fail_tg
        try:
            res = await P.check_proxy("socks5://127.0.0.1:9150")
            check(not res["ok"] and "не отвечает" in res["error"],
                  "прокси молчит → ошибка на TCP-шаге")
        finally:
            P.is_installed, P.probe_tcp, P.probe_telegram = orig_installed, orig_tcp, orig_tg

        # 5. Всё ок — 4 шага, ok=True
        orig_installed = P.is_installed
        orig_tcp, orig_tg = P.probe_tcp, P.probe_telegram
        P.is_installed = lambda: True

        async def ok_tcp(host, port):
            return True, f"Прокси {host}:{port} отвечает"

        async def ok_tg(url):
            return True, "api.telegram.org доступен"

        P.probe_tcp, P.probe_telegram = ok_tcp, ok_tg
        try:
            res = await P.check_proxy("socks5://127.0.0.1:9150")
            check(res["ok"] and len(res["steps"]) == 4 and res["error"] is None,
                  "все шаги зелёные → ok=True, 4 шага")
        finally:
            P.is_installed, P.probe_tcp, P.probe_telegram = orig_installed, orig_tcp, orig_tg

    asyncio.run(run())


def test_probe_tcp_real():
    """TCP-проба на реальный localhost-порт: корректная пара возвращает True."""
    section("Реальная TCP-проба (localhost)")

    async def run():
        import socket
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]

        ok, _ = await P.probe_tcp("127.0.0.1", port)
        check(ok, f"открытый порт {port} → доступен")

        srv.close()
        ok, _ = await P.probe_tcp("127.0.0.1", 1)  # почти наверняка закрыт
        check(not ok, "закрытый порт → недоступен")

    asyncio.run(run())


def main():
    test_validate_proxy_url()
    test_parse_proxy_url()
    test_error_tip()
    test_friendly_error_keeps_original()
    test_check_proxy_short_circuits()
    test_probe_tcp_real()

    print()
    if FAILED:
        print("❌ Провалено: " + ", ".join(FAILED))
        return 1
    print("✅ Все проверки прокси пройдены")
    return 0


if __name__ == "__main__":
    sys.exit(main())
