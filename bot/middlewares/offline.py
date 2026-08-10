"""VIP offline protection: while away, the player has no game actions.

Проверка доступа намеренно открывает и ЗАКРЫВАЕТ свою короткую сессию до
запуска хендлера. Хендлеры бота работают в собственных транзакциях. Раньше
DBSessionMiddleware держал внешнюю read-транзакцию до конца хендлера, а
хендлер внутри открывал вторую сессию и писал в SQLite. Это создавало
взаимную блокировку до стандартного таймаута SQLite (около 5 секунд).
"""
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.orm import joinedload, load_only

from core.database import async_session
from core.models import User, Character
from core.vip import offline_protected

# Ключи контекста общие с BanMiddleware: одна выборка обслуживает обе
# проверки вместо прежних трёх запросов User → Character → User.
_EVENT_USER = "access_user"
_EVENT_CHARACTER = "access_character"


class OfflineProtectionMiddleware(BaseMiddleware):
    """Load player access state once and block actions while VIP is offline."""

    async def __call__(self, handler: Callable, event: TelegramObject,
                       data: Dict[str, Any]) -> Any:
        user_id = getattr(getattr(event, "from_user", None), "id", None)
        user = None
        character = None

        if user_id is not None:
            # joinedload = один короткий SELECT. load_only не тянет десятки
            # игровых полей Character, которые проверке доступа не нужны.
            async with async_session() as session:
                user = (await session.execute(
                    select(User)
                    .where(User.telegram_id == user_id)
                    .options(
                        load_only(User.id, User.is_banned, User.ban_reason),
                        joinedload(User.character).load_only(
                            Character.id,
                            Character.is_vip,
                            Character.vip_until,
                            Character.offline_protected,
                        ),
                    )
                )).unique().scalar_one_or_none()
                if user is not None:
                    character = user.character

            # Объекты содержат только уже загруженные scalar-поля, поэтому
            # безопасно передать их следующей middleware после закрытия сессии.
            data[_EVENT_USER] = user
            data[_EVENT_CHARACTER] = character

        allow_resume = (
            isinstance(event, CallbackQuery)
            and (event.data or "") in {"offline_resume", "offline_toggle"}
        )
        if not allow_resume and character and offline_protected(character):
            if isinstance(event, CallbackQuery):
                await event.answer(
                    "Ты офлайн. Нажми «Вернуться в мир», чтобы продолжить.",
                    show_alert=True,
                )
            elif isinstance(event, Message):
                await event.answer(
                    "🌙 Ты офлайн. Вернись в мир кнопкой в последнем сообщении."
                )
            return None
        return await handler(event, data)
