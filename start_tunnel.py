#!/usr/bin/env python3
"""Ручной запуск панели с публичным адресом (Quick Tunnel).

Обычно ничего запускать не нужно: launch.py сам поднимает туннель при
старте (см. core/tunnel.py, выключается ADMIN_TUNNEL=0). Этот скрипт —
запасной путь на случай отладки: поднимает uvicorn, туннель и печатает
публичный адрес.
"""
import asyncio
import subprocess
import sys
import time

from core import tunnel as tunnel_mod
from admin.config import settings


def main() -> None:
    print("🌑 Запускаю Shadow Lands (панель + Quick Tunnel)…")
    srv = subprocess.Popen(
        [sys.executable, "launch.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        # launch.py сам сохранит адрес в настройки панели; здесь просто
        # печатаем его, когда он появится (до 90 секунд с учётом скачивания).
        url = ""
        for _ in range(90):
            time.sleep(1)
            if srv.poll() is not None:
                print("❌ Сервер завершился раньше времени — смотри лог выше.")
                sys.exit(1)
            try:
                url = asyncio.run(_read_saved_url())
            except Exception:
                url = ""
            if url:
                break

        if url:
            print(f"\n🎉 ПУБЛИЧНЫЙ АДРЕС: {url}")
            print("Он уже сохранён в настройках панели — кнопка «🌐 Открыть")
            print("панель» в боте ведёт на Mini App прямо из Telegram.")
            print("Ctrl+C — остановить.\n")
        else:
            print("⚠️ Адрес не появился за 90 с — смотри лог сервера.")

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        srv.terminate()


async def _read_saved_url() -> str:
    from core.settings_store import get_panel_url
    return await get_panel_url()


if __name__ == "__main__":
    main()
