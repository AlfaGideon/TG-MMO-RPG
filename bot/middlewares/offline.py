"""VIP offline protection: while away, the player has no game actions."""
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, CallbackQuery, Message
from sqlalchemy import select

from core.models import User, Character
from core.vip import offline_protected


class OfflineProtectionMiddleware(BaseMiddleware):
    """Block every interaction except the single return-to-world action."""

    async def __call__(self, handler: Callable, event: TelegramObject,
                       data: Dict[str, Any]) -> Any:
        if isinstance(event, CallbackQuery):
            action = event.data or ""
            if action in {"offline_resume", "offline_toggle"}:
                return await handler(event, data)
        session = data.get("session")
        user_id = getattr(getattr(event, "from_user", None), "id", None)
        if session is not None and user_id is not None:
            user = (await session.execute(
                select(User).where(User.telegram_id == user_id)
            )).scalar_one_or_none()
            character = None
            if user:
                character = (await session.execute(
                    select(Character).where(Character.user_id == user.id)
                )).scalar_one_or_none()
            if character and offline_protected(character):
                if isinstance(event, CallbackQuery):
                    await event.answer("Ты офлайн. Нажми «Вернуться в мир», чтобы продолжить.",
                                       show_alert=True)
                elif isinstance(event, Message):
                    await event.answer("🌙 Ты офлайн. Вернись в мир кнопкой в последнем сообщении.")
                return None
        return await handler(event, data)
