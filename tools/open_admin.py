#!/usr/bin/env python3
"""Ждёт запуска сервера и открывает админку в браузере.

Зачем отдельный скрипт: `python launch.py` занимает консоль до остановки
сервера, поэтому .bat-файл не может открыть браузер «после запуска» —
строка после запуска выполнится только когда сервер уже остановлен.
Этот помощник запускается ФОНОМ (start /b) ещё до launch.py, ждёт, пока
панель реально начнёт отвечать, и только тогда открывает вкладку.

Использование:
    python tools/open_admin.py              # ждать и открыть браузер
    python tools/open_admin.py --print-url  # только напечатать адрес панели
    python tools/open_admin.py --timeout 60 # своё время ожидания (сек)
    python tools/open_admin.py --stop-file X # выйти, если файл X исчез
                                             # (запускающий .bat его удаляет,
                                             #  когда сервер завершился)

Отключить автооткрытие: переменная окружения SL_NO_BROWSER=1
(или ADMIN_NO_BROWSER=1 / NO_BROWSER=1).
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import time
import urllib.error
import urllib.request
import webbrowser

DEFAULT_PORT = 8000
DEFAULT_TIMEOUT = 180.0
POLL_INTERVAL = 0.5

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _port_from_env_file() -> int | None:
    """Читает ADMIN_PORT из .env, не требуя установленных зависимостей."""
    env_path = os.path.join(PROJECT_ROOT, ".env")
    try:
        with open(env_path, "r", encoding="utf-8-sig") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                if key.strip() != "ADMIN_PORT":
                    continue
                value = value.split("#", 1)[0].strip().strip("'\"")
                if value.isdigit():
                    return int(value)
    except OSError:
        pass
    return None


def resolve_port() -> int:
    """Порт панели: переменная окружения → .env → 8000."""
    raw = (os.getenv("ADMIN_PORT") or "").strip()
    if raw.isdigit():
        return int(raw)
    return _port_from_env_file() or DEFAULT_PORT


def resolve_url(port: int | None = None) -> str:
    """Адрес, который нужно открыть в браузере."""
    port = resolve_port() if port is None else port
    return f"http://localhost:{port}"


def browser_disabled() -> bool:
    for name in ("SL_NO_BROWSER", "ADMIN_NO_BROWSER", "NO_BROWSER"):
        if (os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}:
            return True
    return False


def _port_is_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _responds(port: int) -> bool:
    """Панель отвечает по HTTP.

    Любой ответ (200, 303-редирект на /admin-login, 401 и т.п.) означает,
    что сервер уже поднялся — важно лишь, что это не отказ соединения.
    """
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/health", headers={"User-Agent": "shadowlands-launcher"}
    )
    try:
        with urllib.request.urlopen(req, timeout=3):
            return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


def wait_for_server(port: int, timeout: float, stop_file: str | None = None) -> str:
    """Ждёт, пока панель начнёт отвечать.

    Возвращает "ready" / "timeout" / "aborted".

    stop_file — «маячок» запускающего скрипта: пока файл существует, сервер
    ещё стартует. Если файл исчез (launch.py упал или его закрыли), ждать
    дальше бессмысленно — выходим сразу, не оставляя висеть фоновый процесс.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_is_open(port) and _responds(port):
            return "ready"
        if stop_file and not os.path.exists(stop_file):
            return "aborted"
        time.sleep(POLL_INTERVAL)
    return "timeout"


def main() -> int:
    parser = argparse.ArgumentParser(add_help=True, description=__doc__)
    parser.add_argument(
        "--print-url", action="store_true",
        help="напечатать адрес панели и выйти (для .bat/.sh)",
    )
    parser.add_argument(
        "--timeout", type=float, default=float(os.getenv("SL_BROWSER_TIMEOUT") or DEFAULT_TIMEOUT),
        help=f"сколько секунд ждать сервер (по умолчанию {DEFAULT_TIMEOUT:.0f})",
    )
    parser.add_argument(
        "--no-wait", action="store_true",
        help="не ждать сервер — открыть браузер сразу (панель уже запущена)",
    )
    parser.add_argument(
        "--stop-file", default=None,
        help="прекратить ожидание, если этот файл-маячок исчез",
    )
    args = parser.parse_args()

    port = resolve_port()
    url = resolve_url(port)

    if args.print_url:
        print(url)
        return 0

    if browser_disabled():
        print("ℹ️ Автооткрытие браузера отключено (SL_NO_BROWSER=1).")
        return 0

    if not args.no_wait:
        status = wait_for_server(port, args.timeout, args.stop_file)
        if status == "aborted":
            print("ℹ️ Запуск сервера прерван — браузер не открыт.")
            return 1
        if status != "ready":
            print(
                f"⚠️ Панель не ответила за {args.timeout:.0f} сек — браузер не открыт.\n"
                f"   Открой вручную: {url}"
            )
            return 1

    try:
        opened = webbrowser.open(url)
    except Exception:
        opened = False

    if opened:
        print(f"🌐 Открываю админку в браузере: {url}")
        return 0

    print(f"⚠️ Не удалось открыть браузер автоматически. Открой вручную: {url}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
