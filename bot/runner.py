import asyncio
import logging
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.handlers import routers
from bot.middlewares.db import DBSessionMiddleware
from bot.middlewares.dedup import DedupUpdateMiddleware, reset_deduper
from bot.middlewares.offline import OfflineProtectionMiddleware
from bot.middlewares.serialize import SerializeUserMiddleware

logger = logging.getLogger(__name__)


class BotRunner:
    def __init__(self):
        self.bot: Optional[Bot] = None
        self.dp: Optional[Dispatcher] = None
        self._task: Optional[asyncio.Task] = None
        self._portal_sweep_task: Optional[asyncio.Task] = None
        self._spawn_tick_task: Optional[asyncio.Task] = None
        self._bg_tasks: set = set()      # ссылки на fire-and-forget задачи
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
            # Свежий LRU update_id на каждый старт — после рестарта Telegram
            # может прислать старые id, но offset уже сдвинут, а если нет —
            # лучше один раз обработать, чем проглотить «как будто дубль».
            reset_deduper()
            # aiogram 3: wrap_middlewares делает reversed() — первый
            # зарегистрированный middleware = самый внешний (идёт первым).
            # Снаружи внутрь: дедуп → сериализация → БД → офлайн → handler.
            for event_type in (self.dp.message, self.dp.callback_query):
                event_type.middleware(DedupUpdateMiddleware())
                event_type.middleware(SerializeUserMiddleware())
                event_type.middleware(DBSessionMiddleware())
                event_type.middleware(OfflineProtectionMiddleware())
            for router in routers:
                self.dp.include_router(router)

            self._running = True
            self._task = asyncio.create_task(self._poll())
            # Ссылку держим явно: цикл событий хранит задачи слабо,
            # и несохранённый create_task может быть собран GC на полпути
            # (задокументированная ловушка asyncio).
            notice = asyncio.create_task(self._notify_resume_on_start())
            self._bg_tasks.add(notice)
            notice.add_done_callback(self._bg_tasks.discard)
            cleanup = asyncio.create_task(self._cleanup_after_restart())
            self._bg_tasks.add(cleanup)
            cleanup.add_done_callback(self._bg_tasks.discard)
            self._portal_sweep_task = asyncio.create_task(self._portal_sweep_loop())
            self._spawn_tick_task = asyncio.create_task(self._spawn_tick_loop())
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

    async def _cleanup_after_restart(self):
        """Боевое состояние живёт в памяти: после рестарта середина боя
        теряется, а моб так и остался бы «в чужих руках» навсегда —
        неуязвимый и неподвижный (`engaged_by_id` без хозяина). Снимаем
        все захваты при старте."""
        try:
            await asyncio.sleep(1)                     # дать БД подняться
            from sqlalchemy import update
            from core.database import async_session
            from core.models import MobSpawn
            async with async_session() as session:
                res = await session.execute(
                    update(MobSpawn)
                    .where(MobSpawn.engaged_by_id.isnot(None))
                    .values(engaged_by_id=None)
                )
                await session.commit()
            if res.rowcount:
                logger.info(f"Released {res.rowcount} mobs engaged before restart")
        except Exception as e:
            logger.debug(f"engagement cleanup failed: {e}")

    async def _portal_sweep_loop(self):
        """Periodically auto-closes dungeon portals that have been open
        longer than the 2h limit, independent of whether anyone visits the
        admin panel or the portal cell in the meantime."""
        from core.database import async_session
        from core.dungeons import sweep_expired_portals
        from bot.broadcast import notify_dungeon_portal_closed

        while self.is_running():
            try:
                async with async_session() as session:
                    closed = await sweep_expired_portals(session)
                    names = [tpl.name for tpl in closed]
                    await session.commit()
                for name in names:
                    try:
                        await notify_dungeon_portal_closed(self.bot, name)
                    except Exception as e:
                        logger.debug(f"portal auto-close notice failed: {e}")
            except Exception as e:
                logger.debug(f"portal sweep failed: {e}")
            await asyncio.sleep(300)  # check every 5 minutes

    async def _spawn_tick_loop(self):
        """Живой мир: держит популяцию мобов на лимите и двигает их по карте.

        Убили моба — через его respawn_seconds появится новый, но сверх
        Mob.population никто не заспавнится. Ходят мобы только там, где им
        разрешено (слабые могут уйти в локации выше уровнем, сильные к
        слабым — нет).
        """
        from core.database import async_session
        from core.spawns import tick

        while self.is_running():
            try:
                async with async_session() as session:
                    stats = await tick(session)
                    # Заодно возвращаем продавцам протухшие лоты аукциона
                    from core.auction import sweep_expired
                    returned = await sweep_expired(session)
                    if returned:
                        stats["lots_returned"] = len(returned)
                    await session.commit()
                if stats.get("spawned") or stats.get("moved"):
                    logger.debug(f"world tick: {stats}")
            except Exception as e:
                logger.debug(f"spawn tick failed: {e}")
            await asyncio.sleep(20)

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

        if self._portal_sweep_task:
            self._portal_sweep_task.cancel()
            try:
                await self._portal_sweep_task
            except asyncio.CancelledError:
                pass
            self._portal_sweep_task = None

        if self._spawn_tick_task:
            self._spawn_tick_task.cancel()
            try:
                await self._spawn_tick_task
            except asyncio.CancelledError:
                pass
            self._spawn_tick_task = None

        if self.dp:
            await self.dp.emit_shutdown()
        if self.bot:
            await self.bot.session.close()
            self.bot = None

        logger.info("Bot stopped")
        return True


bot_runner = BotRunner()
