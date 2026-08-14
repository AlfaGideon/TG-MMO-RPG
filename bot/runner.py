import asyncio
import logging
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramConflictError, TelegramUnauthorizedError

from bot.handlers import routers
from bot.middlewares.ban import BanMiddleware
from bot.middlewares.dedup import DedupUpdateMiddleware, reset_deduper
from bot.middlewares.offline import OfflineProtectionMiddleware
from bot.middlewares.serialize import SerializeUserMiddleware
from bot.proxy import friendly_error, is_installed, validate_proxy_url

logger = logging.getLogger(__name__)

CONFLICT_MESSAGE = (
    "⚠️ Конфликт: Telegram сообщает, что с этим токеном уже работает "
    "ДРУГОЙ экземпляр бота (terminated by other getUpdates request). "
    "Значит, запущено два сервера/бота одновременно: лишнее окно с "
    "launch.py или run.bat, отдельный python -m bot.main, либо старый "
    "процесс, оставшийся после «Обновить с GitHub». Найди и закрой "
    "лишний процесс, затем нажми «Запустить бота»."
)

AUTH_MESSAGE = (
    "❌ Telegram отклонил токен бота (Unauthorized). Токен неверный или "
    "был отозван. Откройте @BotFather → /mybots → выберите бота → "
    "API Token, скопируйте новый токен целиком, сохраните его в Настройках "
    "и снова нажмите «Запустить бота»."
)
STARTUP_CHECK_TIMEOUT = 15.0


class ConflictAwareSession(AiohttpSession):
    """AiohttpSession, замечающий конфликт polling и потерю авторизации.

    aiogram сам ретраит ошибки getUpdates бесконечно: два экземпляра бота
    могут вечно «драться», а неверный токен — печатать Unauthorized каждые
    несколько секунд. Сессия передаёт фатальные события в BotRunner, чтобы
    тот остановил polling и показал понятное сообщение.
    """

    def __init__(self, on_conflict, on_unauthorized=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._on_conflict = on_conflict
        self._on_unauthorized = on_unauthorized

    async def __call__(self, bot, method, timeout=None):
        try:
            return await super().__call__(bot, method, timeout=timeout)
        except TelegramConflictError as e:
            if self._on_conflict:
                self._on_conflict(e)
            raise
        except TelegramUnauthorizedError as e:
            # Без этого aiogram бесконечно повторяет getUpdates и каждые
            # несколько секунд печатает «Failed to fetch updates ...
            # Unauthorized». Runner остановит polling после первой ошибки.
            if self._on_unauthorized:
                self._on_unauthorized(e)
            raise


class BotRunner:
    def __init__(self):
        self.bot: Optional[Bot] = None
        self.dp: Optional[Dispatcher] = None
        self._task: Optional[asyncio.Task] = None
        self._portal_sweep_task: Optional[asyncio.Task] = None
        self._spawn_tick_task: Optional[asyncio.Task] = None
        self._dividend_task: Optional[asyncio.Task] = None
        self._bg_tasks: set = set()      # ссылки на fire-and-forget задачи
        self._running = False
        self.last_error: Optional[str] = None
        self.proxy_url: str = ""
        # Защита от двойного запуска: два одновременных start() (например,
        # двойной клик по «Запустить бота») создали бы два polling-цикла и
        # конфликт getUpdates с самим собой.
        self._start_lock = asyncio.Lock()
        self._conflicts = 0              # счётчик TelegramConflictError подряд
        self._conflict_worker: Optional[asyncio.Task] = None
        self._auth_worker: Optional[asyncio.Task] = None

    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def _ensure_dispatcher(self):
        if self.dp is not None:
            return

        self.dp = Dispatcher()
        # Свежий LRU update_id на каждый старт — после рестарта Telegram
        # может прислать старые id, но offset уже сдвинут, а если нет —
        # лучше один раз обработать, чем проглотить «как будто дубль».
        reset_deduper()
        # aiogram 3: wrap_middlewares делает reversed() — первый
        # зарегистрированный middleware = самый внешний (идёт первым).
        # Снаружи внутрь: дедуп → сериализация → единая короткая проверка
        # игрока/offline → бан → handler. Отдельного DBSessionMiddleware здесь
        # быть не должно: хендлеры открывают собственные сессии, а внешняя
        # read-транзакция удерживала SQLite lock примерно на 5 секунд.
        for event_type in (self.dp.message, self.dp.callback_query):
            event_type.middleware(DedupUpdateMiddleware())
            event_type.middleware(SerializeUserMiddleware())
            event_type.middleware(OfflineProtectionMiddleware())
            event_type.middleware(BanMiddleware())
        for router in routers:
            self.dp.include_router(router)

    async def _close_current_bot(self):
        if self.bot:
            try:
                await self.bot.session.close()
            except Exception:
                pass
            self.bot = None

    async def _validate_bot(self):
        """Проверить токен до запуска polling, а не после ложного «успеха»."""
        return await asyncio.wait_for(
            self.bot.get_me(), timeout=STARTUP_CHECK_TIMEOUT
        )

    async def start(self, token: str, proxy_url: str = "") -> bool:
        async with self._start_lock:
            if self.is_running():
                logger.info("Bot already running")
                return False

            token = (token or "").strip()
            if not token:
                self.last_error = (
                    "Токен бота не задан. Скопируйте его у @BotFather, "
                    "сохраните в Настройках и повторите запуск."
                )
                return False

            # После сетевой ошибки polling мог остановиться сам, не проходя через
            # ручной stop(). Закрываем старую HTTP-сессию, но Dispatcher оставляем:
            # aiogram Router нельзя прикрепить к новому Dispatcher повторно. Именно
            # это давало ошибку «Router is already attached ...» при следующем старте.
            await self._close_current_bot()

            proxy_url = (proxy_url or "").strip()
            # Пред-проверки прокси: вместо сырого английского исключения aiogram
            # админ получает понятную ошибку и знает, что делать.
            if proxy_url:
                url_err = validate_proxy_url(proxy_url)
                if url_err:
                    self.last_error = url_err
                    logger.error(f"Invalid proxy URL {proxy_url!r}: {url_err}")
                    return False
                if not is_installed():
                    self.last_error = (
                        "Не установлен пакет aiohttp-socks — без него aiogram не умеет "
                        "ходить через SOCKS-прокси. Установите: pip install aiohttp-socks, "
                        "затем перезапустите сервер и нажмите «Запустить бота»."
                    )
                    logger.error(f"Cannot start bot with proxy: {self.last_error}")
                    return False

            try:
                # Свежий счётчик конфликтов на каждый старт.
                self._conflicts = 0
                self._conflict_worker = None
                self._auth_worker = None
                session = ConflictAwareSession(
                    on_conflict=self._note_conflict,
                    on_unauthorized=self._note_unauthorized,
                    proxy=proxy_url or None,
                )
                bot_kwargs = {
                    "token": token,
                    "default": DefaultBotProperties(parse_mode=ParseMode.HTML),
                    "session": session,
                }

                self.bot = Bot(**bot_kwargs)
                self.proxy_url = proxy_url
                self.last_error = None

                # Ключевой preflight: getMe возвращает Unauthorized для
                # неверного/отозванного токена. До успешного ответа НЕ ставим
                # running=True и НЕ запускаем start_polling, поэтому панель не
                # показывает ложный зелёный статус, а aiogram не ретраит ошибку.
                me = await self._validate_bot()
                reset_deduper()
                self._ensure_dispatcher()

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
                self._dividend_task = asyncio.create_task(self._dividend_loop())
                username = getattr(me, "username", None)
                who = f" @{username}" if username else ""
                if proxy_url:
                    logger.info("Bot%s started via Telegram proxy", who)
                else:
                    logger.info("Bot%s started", who)
                return True
            except TelegramUnauthorizedError:
                self.last_error = AUTH_MESSAGE
                logger.error(AUTH_MESSAGE)
                self._running = False
                await self._close_current_bot()
                return False
            except asyncio.TimeoutError:
                raw = (
                    f"Telegram не ответил на проверку токена за "
                    f"{int(STARTUP_CHECK_TIMEOUT)} секунд."
                )
                self.last_error = friendly_error(raw, proxy_url) if proxy_url else (
                    raw + " Проверьте интернет/доступ к api.telegram.org и повторите запуск."
                )
                logger.error(self.last_error)
                self._running = False
                await self._close_current_bot()
                return False
            except Exception as e:
                raw = str(e)
                low = raw.lower()
                if "unauthorized" in low or "token is invalid" in low:
                    self.last_error = AUTH_MESSAGE
                elif proxy_url:
                    self.last_error = friendly_error(raw, proxy_url)
                else:
                    self.last_error = raw
                logger.error("Failed to start bot: %s", self.last_error)
                self._running = False
                await self._close_current_bot()
                return False


    def _note_unauthorized(self, exc: TelegramUnauthorizedError):
        """Остановить бесконечные ретраи, если токен отозвали во время работы."""
        self.last_error = AUTH_MESSAGE
        # Во время стартового getMe running ещё False: исключение обработает
        # start() синхронно. Worker нужен только действующему polling.
        if not self._running:
            return
        logger.error("Telegram authorization lost; stopping bot: %s", exc)
        if self._auth_worker is None or self._auth_worker.done():
            self._auth_worker = asyncio.create_task(self._handle_unauthorized())
            self._bg_tasks.add(self._auth_worker)
            self._auth_worker.add_done_callback(self._bg_tasks.discard)

    async def _handle_unauthorized(self):
        """Stop polling immediately; preserve the actionable Russian error."""
        if self.is_running():
            await self.stop()
        self.last_error = AUTH_MESSAGE

    def _note_conflict(self, exc: TelegramConflictError):
        """TelegramConflictError из любого запроса (обычно getUpdates)."""
        logger.error("TelegramConflictError: %s", exc)
        self._conflicts += 1
        if self._conflict_worker is None or self._conflict_worker.done():
            self._conflict_worker = asyncio.create_task(self._handle_conflict())
            self._bg_tasks.add(self._conflict_worker)
            self._conflict_worker.add_done_callback(self._bg_tasks.discard)

    async def _handle_conflict(self):
        """Показывает причину конфликта; при повторных конфликтах — стоп.

        Единичный конфликт (второй экземпляр уже умер) переживаем и
        продолжаем работу. Если конфликты повторяются — второй экземпляр
        жив, и бесконечная «драка» getUpdates бессмысленна: останавливаем
        polling, чтобы админ увидел причину и закрыл лишний процесс.
        """
        prev_error = self.last_error
        self.last_error = CONFLICT_MESSAGE
        await asyncio.sleep(2.5)
        if self._conflicts >= 2:
            await self.stop()
            self.last_error = (
                CONFLICT_MESSAGE
                + "\n\nБот остановлен, чтобы два экземпляра не конфликтовали. "
                  "Закрой лишний процесс и нажми «Запустить бота»."
            )
        else:
            self.last_error = prev_error

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

    async def _dividend_loop(self):
        """Дивиденды вкладчикам городских лавок раз в сутки.

        Вклады принимались и раньше (`core/investments.invest_in_town`),
        но выплат не было вовсе: колонка `earned_dividends` не росла.
        Цикл начисляет долю и сообщает вкладчику в личку.
        """
        from core.database import async_session
        from core.investments import pay_dividends, DIVIDEND_PERIOD_HOURS

        while self.is_running():
            await asyncio.sleep(DIVIDEND_PERIOD_HOURS * 3600)
            try:
                async with async_session() as session:
                    payouts = await pay_dividends(session)
                    await session.commit()
                for pay in payouts:
                    if not pay.get("telegram_id"):
                        continue
                    try:
                        await self.bot.send_message(
                            pay["telegram_id"],
                            f"🏦 <b>Дивиденды с лавки</b>\n\n"
                            f"«{pay['location_name']}» принесла тебе "
                            f"<b>+{pay['amount']}</b>🟤.",
                            parse_mode="HTML")
                    except Exception as e:
                        logger.debug(f"dividend notice failed: {e}")
            except Exception as e:
                logger.debug(f"dividend payout failed: {e}")

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
            # Через прокси типичная смерть polling-а — недоступный Tor/сеть.
            # Подменяем сырое исключение на понятную подсказку (с оригиналом внутри).
            if self.proxy_url:
                self.last_error = friendly_error(str(e), self.proxy_url)
            else:
                self.last_error = str(e)
            logger.error(f"Bot polling error: {e}")
        finally:
            self._running = False
            # Если polling упал сам (например, сеть/Telegram недоступны),
            # фоновые циклы не должны ожить повторно при следующем старте.
            for task in (self._portal_sweep_task, self._spawn_tick_task,
                         self._dividend_task):
                if task and not task.done():
                    task.cancel()
            self._portal_sweep_task = None
            self._spawn_tick_task = None
            self._dividend_task = None
            await self._close_current_bot()

    async def stop(self) -> bool:
        async with self._start_lock:
            current = asyncio.current_task()
            if not self.is_running():
                logger.info("Bot not running")
                current = asyncio.current_task()
                for task in list(self._bg_tasks):
                    if task and task is not current and not task.done():
                        task.cancel()
                self._bg_tasks.clear()
                await self._close_current_bot()
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

            if self._dividend_task:
                self._dividend_task.cancel()
                try:
                    await self._dividend_task
                except asyncio.CancelledError:
                    pass
                self._dividend_task = None

            if self.dp:
                await self.dp.emit_shutdown()
            if self.bot:
                await self.bot.session.close()
                self.bot = None

            logger.info("Bot stopped")
            return True


bot_runner = BotRunner()
