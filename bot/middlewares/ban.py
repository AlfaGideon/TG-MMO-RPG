"""Бан: заблокированный админом игрок не может действовать в боте.

Любой апдейт (сообщение или кнопка) от забаненного пользователя
отклоняется ещё до хендлера. /start тоже глушится — игрок видит причину
бана и больше ничего.
"""
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, CallbackQuery, Message
from sqlalchemy import select

from core.models import User


class BanMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
                       event: TelegramObject, data: Dict[str, Any]) -> Any:
        tg = getattr(getattr(event, "from_user", None), "id", None)
        session = data.get("session")
        if tg is not None and session is not None:
            user = (await session.execute(
                select(User).where(User.telegram_id == tg)
            )).scalar_one_or_none()
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
                return None  # не пускаем к хендлеру
        return await handler(event, data)
