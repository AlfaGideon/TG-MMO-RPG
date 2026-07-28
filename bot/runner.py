import asyncio
import logging
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.handlers import routers
from bot.middlewares.db import DBSessionMiddleware

logger = logging.getLogger(__name__)


class BotRunner:
    def __init__(self):
        self.bot: Optional[Bot] = None
        self.dp: Optional[Dispatcher] = None
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    async def start(self, token: str) -> bool:
        if self.is_running():
            logger.info("Bot already running")
            return False

        try:
            self.bot = Bot(
                token=token,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML)
            )
            self.dp = Dispatcher()
            self.dp.message.middleware(DBSessionMiddleware())
            self.dp.callback_query.middleware(DBSessionMiddleware())
            for router in routers:
                self.dp.include_router(router)

            self._running = True
            self._task = asyncio.create_task(self._poll())
            asyncio.create_task(self._notify_resume_on_start())
            logger.info("Bot started")
            return True
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            self._running = False
            return False

    async def _notify_resume_on_start(self):
        """Fire-and-forget: right after (re)starting, nudge players whose
        action was likely interrupted by the restart to repeat it."""
        try:
            await asyncio.sleep(2)  # let polling settle first
            from bot.broadcast import notify_resume_interrupted_actions
            count = await notify_resume_interrupted_actions(self.bot)
            if count:
                logger.info(f"Sent resume-action notices to {count} player(s)")
        except Exception as e:
            logger.debug(f"resume notification pass failed: {e}")

    async def _poll(self):
        try:
            await self.dp.start_polling(self.bot)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Bot polling error: {e}")
        finally:
            self._running = False

    async def stop(self) -> bool:
        if not self.is_running():
            logger.info("Bot not running")
            return False

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self.dp:
            await self.dp.emit_shutdown()
        if self.bot:
            await self.bot.session.close()
            self.bot = None

        logger.info("Bot stopped")
        return True


bot_runner = BotRunner()
