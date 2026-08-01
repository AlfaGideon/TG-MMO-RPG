#!/usr/bin/env python3
"""
Единая точка входа для Shadow Lands.
Запускает веб-админку и бота в одном процессе.
"""
import os
import sys
import asyncio
import logging

import uvicorn
from sqlalchemy import select

from core.database import init_db, async_session
from core.migrations import run_migrations
from core.seed import seed_database
from core.seed_content import seed_content
from core.models import AppSetting
from bot.runner import bot_runner
from admin.main import app, settings as admin_settings, get_bot_proxy_url

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("launcher")


async def try_start_bot_from_db():
    async with async_session() as session:
        result = await session.execute(
            select(AppSetting).where(AppSetting.key == "bot_token")
        )
        setting = result.scalar_one_or_none()
        if setting and setting.value.strip():
            ok = await bot_runner.start(
                setting.value.strip(), await get_bot_proxy_url()
            )
            if ok:
                logger.info("Bot auto-started from database token")
            else:
                logger.warning("Failed to auto-start bot")
        else:
            logger.info("No bot token in database. Go to /settings to configure.")


async def _seed_extra_content():
    """Классы, материалы, таблицы лута, рецепты и мобы-популяции.

    В отличие от seed_database отрабатывает и на уже существующей базе —
    поэтому обновление кода само подтягивает новый контент.
    """
    from core.spawns import ensure_all_populations

    async with async_session() as session:
        stats = await seed_content(session)
        spawned = await ensure_all_populations(session)
        await session.commit()
    logger.info(f"Content seed: {stats}, mob spawns created: {spawned}")


def _port_busy(host: str, port: int) -> bool:
    """Занят ли порт: если да — сервер уже запущен (второй экземпляр не нужен)."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.settimeout(1)
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


def main():
    os.makedirs("data", exist_ok=True)

    if _port_busy(admin_settings.ADMIN_HOST, admin_settings.ADMIN_PORT):
        print(
            f"❌ Порт {admin_settings.ADMIN_PORT} уже занят — похоже, сервер "
            "уже запущен (другое окно/терминал)."
        )
        print(
            "   Закрой лишний процесс, иначе бот будет конфликтовать сам с "
            "собой (TelegramConflictError)."
        )
        sys.exit(1)

    # Init DB synchronously before uvicorn starts
    asyncio.run(run_migrations())
    asyncio.run(seed_database())
    asyncio.run(_seed_extra_content())

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
