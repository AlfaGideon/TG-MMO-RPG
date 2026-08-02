import asyncio
import logging
import os

from core.database import init_db
from core.seed import seed_database
from bot.runner import bot_runner

logging.basicConfig(level=logging.INFO)


async def main():
    os.makedirs("data", exist_ok=True)
    await init_db()
    await seed_database()

    # Автономный бот работает без панели, значит Quick Tunnel никто не
    # поднимает — сохранённый в БД адрес *.trycloudflare.com гарантированно
    # мёртв (домен живёт только вместе со своим процессом cloudflared).
    # Без этой очистки кнопка «🌐 Открыть панель» вела бы на ошибку 1033.
    from core.settings_store import (
        PANEL_URL_KEY, get_setting, is_temporary_tunnel_url, set_panel_url,
    )
    saved = await get_setting(PANEL_URL_KEY)
    if is_temporary_tunnel_url(saved):
        logging.info(f"Адрес прошлого Quick Tunnel ({saved}) устарел — очищаю.")
        await set_panel_url("")

    # Try to read token from env for standalone mode
    from bot.config import settings
    if settings.BOT_TOKEN:
        await bot_runner.start(settings.BOT_TOKEN, settings.TELEGRAM_PROXY_URL)
        # Keep running
        while bot_runner.is_running():
            await asyncio.sleep(1)
    else:
        print("No BOT_TOKEN set. Use admin panel to configure and start the bot.")


if __name__ == "__main__":
    asyncio.run(main())
