"""«Лента мира»: события игры → канал сообщества.

Почему подписка на шину, а не вызовы из хендлеров. События мира уже
публикуются в `core/realtime` (порталы, боссы, катаклизмы, карма, ломбард
— см. пункт № 70). Дописывать в каждый хендлер ещё и отправку в чат
значило бы держать два списка мест, которые обязаны совпадать. Здесь одна
подписка: что попало в ленту админки — попадёт и в канал.

Фильтр обязателен. В шину летит и мелочь вроде `player_move` (каждый шаг
каждого героя): в общий чат такое слать нельзя, группа превратится в
пулемёт. Поэтому пересылаются только события из `FEED_EVENTS` — те, что
интересны всем, а не одному игроку.
"""
import asyncio
import logging

from core import realtime as RT

logger = logging.getLogger(__name__)

FEED_CHANNEL = "world"          # ключ канала из core/community.DEFAULT_CHANNELS

# Что достойно общего чата. Намеренно узкий список: `player_move`,
# `chest_opened`, `economy_tick` и прочая рутина сюда не входят.
FEED_EVENTS = {
    "portal_opened",
    "portal_closed",
    "cataclysm_started",
    "boss_spawned",
    "boss_defeated",
    "outpost_captured",
    "player_levelup",
    "server_record",
    "dividends_paid",
}

# Пауза между отправками: Telegram не любит очередь сообщений в одну тему.
MIN_INTERVAL = 2.0


class WorldFeed:
    """Фоновая задача: читает шину и пересылает избранное в канал."""

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._queue: asyncio.Queue | None = None
        self._last_sent = 0.0

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self):
        """Запустить подписку. Повторный вызов ничего не ломает."""
        if self.running:
            return False
        self._queue = await RT.subscribe()
        self._task = asyncio.create_task(self._loop())
        logger.info("community: лента мира подписана на шину событий")
        return True

    async def stop(self):
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._queue is not None:
            await RT.unsubscribe(self._queue)
            self._queue = None

    async def _loop(self):
        from bot import community_bridge as bridge

        while True:
            try:
                event = await self._queue.get()
            except asyncio.CancelledError:
                return
            except Exception:
                continue

            etype = (event or {}).get("type", "")
            if etype not in FEED_EVENTS:
                continue
            try:
                if not await bridge.is_enabled():
                    # Мост выключен — в журнал канала всё равно пишем:
                    # лента мира внутри игры не должна пустовать.
                    pass
                text = RT.format_radar_event(event)
                await bridge.announce(FEED_CHANNEL, text)
                # Разрежаем поток, чтобы не упереться в лимиты Telegram.
                await asyncio.sleep(MIN_INTERVAL)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.debug("community: событие %s не ушло в ленту: %s",
                             etype, exc)


world_feed = WorldFeed()
