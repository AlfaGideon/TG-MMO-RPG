"""Безопасное редактирование сообщений бота.

Экран локации и экран боя — это ФОТО с подписью (карта локации / портрет
моба). Telegram разрешает editMessageText только сообщениям с текстом; для
фото-сообщений существует editMessageCaption. Раньше кнопки на таких экранах
(«🔍 Осмотреться», «Атаковать», «Отдых» и т.п.) звали edit_text и падали с
«Bad Request: there is no text in the message to edit» — кнопка выглядела
мёртвой, а в лог сыпались исключения.

safe_edit_text сам выбирает правильный способ:
  * текстовое сообщение  → edit_text;
  * фото/видео/документ  → edit_caption (правка подписи, фото остаётся);
  * если сообщение вообще нельзя отредактировать — шлёт новое сообщение.
«message is not modified» (контент не изменился) тихо проглатывается —
это не ошибка, а шум Telegram.
"""
import logging

from aiogram.exceptions import TelegramBadRequest

logger = logging.getLogger(__name__)

_MEDIA_ATTRS = (
    "photo", "video", "animation", "document",
    "audio", "voice", "video_note",
)


def _message(event):
    """event может быть CallbackQuery (берём его .message) или Message."""
    msg = getattr(event, "message", None)
    if msg is not None and getattr(msg, "answer", None) is not None:
        return msg
    return event


def _has_media(msg) -> bool:
    return any(getattr(msg, attr, None) is not None for attr in _MEDIA_ATTRS)


async def safe_edit_text(event, text, reply_markup=None, parse_mode="HTML", **kwargs):
    """Правит сообщение (текст или подпись фото), при неудаче шлёт новое."""
    msg = _message(event)
    if msg is None:
        return

    edit_kwargs = dict(reply_markup=reply_markup, parse_mode=parse_mode, **kwargs)

    if getattr(msg, "text", None) is not None:
        try:
            await msg.edit_text(text=text, **edit_kwargs)
            return
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                return
            logger.debug("edit_text failed, fallback to new message: %s", e)
        except Exception as e:  # noqa: BLE001
            logger.debug("edit_text failed, fallback to new message: %s", e)
    elif _has_media(msg):
        try:
            await msg.edit_caption(caption=text, **edit_kwargs)
            return
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                return
            logger.debug("edit_caption failed, fallback to new message: %s", e)
        except Exception as e:  # noqa: BLE001
            logger.debug("edit_caption failed, fallback to new message: %s", e)

    # Сообщение нельзя отредактировать (другой тип/старое) — шлём новое.
    try:
        await msg.answer(text=text, **edit_kwargs)
    except Exception as e:  # noqa: BLE001
        logger.warning("safe_edit_text fallback answer failed: %s", e)
