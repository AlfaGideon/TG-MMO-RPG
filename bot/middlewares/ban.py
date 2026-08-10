"""Бан: заблокированный админом игрок не может действовать в боте.

Состояние пользователя загружает OfflineProtectionMiddleware одной короткой
выборкой вместе с VIP-флагами. Запасная выборка нужна только если middleware
используется отдельно (например, в тесте или стороннем Dispatcher).
"""
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, CallbackQuery, Message
from sqlalchemy import select

from core.database import async_session
from core.models import User
from bot.middlewares.offline import _EVENT_USER


class BanMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
                       event: TelegramObject, data: Dict[str, Any]) -> Any:
        tg = getattr(getattr(event, "from_user", None), "id", None)
        if _EVENT_USER in data:
            user = data.get(_EVENT_USER)
        elif tg is not None:
            # Без внешней долгоживущей транзакции: закрываем read-сессию до
            # вызова хендлера, чтобы его запись не ждала SQLite busy_timeout.
            async with async_session() as session:
                user = (await session.execute(
                    select(User).where(User.telegram_id == tg)
                )).scalar_one_or_none()
        else:
            user = None

        if user and user.is_banned:
            reason = f"\n\nПричина: {user.ban_reason}" if user.ban_reason else ""
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer("🚫 Вы заблокированы.", show_alert=True)
                except Exception:
                    pass
            elif isinstance(event, Message):
                try:
                    await event.answer(
                        f"🚫 <b>Вы заблокированы администратором.</b>{reason}\n\n"
                        "<i>Все действия в игре недоступны.</i>",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
            return None
        return await handler(event, data)
