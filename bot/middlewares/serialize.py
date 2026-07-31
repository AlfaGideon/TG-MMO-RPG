"""Сериализация апдейтов одного пользователя.

Telegram досылает колбэки повторно (двойной тап, ретрай клиента), а
aiogram раскладывает их по параллельным задачам. Пока апдейт одного
пользователя не обработан, следующий его апдейт ждёт — повторный тап
не может сработать на «устаревшем» состоянии (дуп предметов, двойные
списания золота, двойное вскрытие сундука).

Разным пользователям друг другу не мешаем: замок поюзерный.
"""
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.locks import for_user


class SerializeUserMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
                       event: TelegramObject, data: Dict[str, Any]) -> Any:
        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)
        async with for_user(user.id):
            return await handler(event, data)
