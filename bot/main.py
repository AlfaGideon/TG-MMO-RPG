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
