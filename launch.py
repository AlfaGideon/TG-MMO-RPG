#!/usr/bin/env python3
"""
Единая точка входа для Shadow Lands.
Запускает веб-админку и бота в одном процессе.
"""
import os
import asyncio
import logging

import uvicorn
from sqlalchemy import select

from core.database import init_db, async_session
from core.migrations import run_migrations
from core.seed import seed_database
from core.models import AppSetting
from bot.runner import bot_runner
from admin.main import app, settings as admin_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("launcher")


async def try_start_bot_from_db():
    async with async_session() as session:
        result = await session.execute(
            select(AppSetting).where(AppSetting.key == "bot_token")
        )
        setting = result.scalar_one_or_none()
        if setting and setting.value.strip():
            ok = await bot_runner.start(setting.value.strip())
            if ok:
                logger.info("Bot auto-started from database token")
            else:
                logger.warning("Failed to auto-start bot")
        else:
            logger.info("No bot token in database. Go to /settings to configure.")


def main():
    os.makedirs("data", exist_ok=True)

    # Init DB synchronously before uvicorn starts
    asyncio.run(run_migrations())
    asyncio.run(seed_database())

    logger.info(f"Starting admin panel on http://{admin_settings.ADMIN_HOST}:{admin_settings.ADMIN_PORT}")
    uvicorn.run(
        "admin.main:app",
        host=admin_settings.ADMIN_HOST,
        port=admin_settings.ADMIN_PORT,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
