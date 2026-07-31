"""Дедупликация Telegram-апдейтов по update_id.

Telegram и клиенты иногда доставляют один update дважды (ретрай long-poll,
двойной getUpdates при двух процессах/рестарте, повтор callback). Без
фильтра хендлер отрабатывает дважды: два /start-ответа, два edit одного
сообщения → «message is not modified».

Фильтр стоит ПЕРВЫМ middleware: повтор даже не доходит до сериализации
и БД. LRU-множество ограничено, чтобы не разрастаться вечно.
"""
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update


_SEEN_MAX = 4000


class UpdateIdDeduper:
    """Потокобезопасный (в рамках одного event loop) LRU-набор update_id."""

    def __init__(self, maxlen: int = _SEEN_MAX):
        self._seen: OrderedDict[int, bool] = OrderedDict()
        self._maxlen = max(1, int(maxlen))

    def seen_before(self, update_id: int) -> bool:
        """True = дубль. False = новый (и уже помечен)."""
        try:
            uid = int(update_id)
        except (TypeError, ValueError):
            return False
        if uid in self._seen:
            self._seen.move_to_end(uid)
            return True
        self._seen[uid] = True
        while len(self._seen) > self._maxlen:
            self._seen.popitem(last=False)
        return False

    def clear(self) -> None:
        self._seen.clear()

    def __len__(self) -> int:
        return len(self._seen)

    def __contains__(self, update_id: int) -> bool:
        try:
            return int(update_id) in self._seen
        except (TypeError, ValueError):
            return False


# Один процесс — один дедупер. При рестарте бота сбрасывается вместе с ним.
_global_deduper = UpdateIdDeduper()


def get_deduper() -> UpdateIdDeduper:
    return _global_deduper


def reset_deduper() -> None:
    """Для тестов: очистить глобальный набор."""
    _global_deduper.clear()


def _extract_update_id(event: TelegramObject, data: Dict[str, Any]) -> Optional[int]:
    """Достать update_id из event.bot context / data / вложенного Update."""
    # aiogram 3 кладёт raw Update в data["event_update"]
    upd = data.get("event_update")
    if upd is not None:
        uid = getattr(upd, "update_id", None)
        if uid is not None:
            return int(uid)
    if isinstance(event, Update):
        return int(event.update_id)
    # fallback: иногда update лежит на event
    uid = getattr(event, "update_id", None)
    if uid is not None:
        return int(uid)
    return None


class DedupUpdateMiddleware(BaseMiddleware):
    """Глотает повторные апдейты с тем же update_id."""

    def __init__(self, deduper: Optional[UpdateIdDeduper] = None):
        self.deduper = deduper or get_deduper()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        uid = _extract_update_id(event, data)
        if uid is not None and self.deduper.seen_before(uid):
            return None
        return await handler(event, data)
