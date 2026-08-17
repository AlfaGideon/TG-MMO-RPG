"""Мост между игрой и супергруппой сообщества.

Решения, которые стоит понимать до чтения кода.

**Источник правды — игра, а не Telegram.** Каталог каналов и права лежат в
`core/community.py`. Здесь только транспорт: создать тему, отправить в неё
текст, принять текст обратно. Если тему удалят руками, канал в игре
уцелеет — мост заведёт тему заново и перепривяжет `thread_id`.

**Почему темы создаются лениво.** Форум-тема появляется при первой
надобности (`ensure_topic`), а не пачкой на старте: иначе в группе висели
бы десятки пустых веток для гильдий, которых ещё нет.

**Отключённый мост — это норма.** Пока в настройках нет `community_chat_id`,
все функции тихо возвращают `None`. Чат внутри игры при этом работает:
сообщения пишутся в БД, их видно в боте и в панели. Так проект не ломается
у того, кто группу не заводил.

**Обратный поток фильтруется по теме.** Сообщение из группы принимается,
только если его `message_thread_id` привязан к каналу. Болтовня в «General»
супергруппы игру не касается.
"""
import logging

from core.community import (ChannelAccess, attach_tg_id, bind_thread,
                            by_thread, ensure_default_channels, list_channels,
                            post as post_message)
from core.database import async_session
from core.settings_store import get_setting, set_setting

logger = logging.getLogger(__name__)

CHAT_ID_KEY = "community_chat_id"        # id супергруппы с темами
ENABLED_KEY = "community_bridge_enabled"

# Цвета тем Telegram принимает только из фиксированного списка.
TOPIC_COLORS = [0x6FB9F0, 0xFFD67E, 0xCB86DB, 0x8EEE98, 0xFF93B2, 0xFB6F5F]


async def get_chat_id() -> str:
    return (await get_setting(CHAT_ID_KEY, "")).strip()


async def set_chat_id(value: str) -> str:
    value = (value or "").strip()
    await set_setting(CHAT_ID_KEY, value)
    return value


async def is_enabled() -> bool:
    """Мост включён, только если задана группа и он не выключен вручную."""
    if not await get_chat_id():
        return False
    return (await get_setting(ENABLED_KEY, "1")).strip() not in ("0", "false", "")


async def set_enabled(flag: bool) -> None:
    await set_setting(ENABLED_KEY, "1" if flag else "0")


def _bot():
    """Живой экземпляр бота или None, если он остановлен."""
    try:
        from bot.runner import bot_runner

        bot = getattr(bot_runner, "bot", None)
        return bot if getattr(bot_runner, "running", False) else bot
    except Exception:
        return None


async def ensure_topic(session, channel, bot=None):
    """Создать тему под канал, если её ещё нет. Возвращает thread_id.

    Тема заводится лениво и переживает ручное удаление: если Telegram
    отвечает ошибкой на отправку, `send_to_channel` сбрасывает привязку и
    зовёт эту функцию снова.
    """
    chat_id = await get_chat_id()
    if not chat_id:
        return None
    bot = bot or _bot()
    if bot is None:
        return None
    if channel.thread_id and str(channel.chat_id) == str(chat_id):
        return channel.thread_id

    try:
        color = TOPIC_COLORS[abs(hash(channel.key)) % len(TOPIC_COLORS)]
        topic = await bot.create_forum_topic(
            chat_id=chat_id,
            name=channel.label()[:128],
            icon_color=color,
        )
    except Exception as exc:
        # Нет прав, группа без тем, бот не админ — не роняем игру.
        logger.warning("community: не удалось создать тему %s: %s",
                       channel.key, exc)
        return None

    await bind_thread(session, channel.key, chat_id, topic.message_thread_id)
    logger.info("community: тема %s создана (thread=%s)",
                channel.key, topic.message_thread_id)
    return topic.message_thread_id


async def send_to_channel(session, channel, text: str, bot=None) -> int | None:
    """Отправить текст в тему канала. Возвращает id сообщения Telegram.

    Одна попытка перепривязки: если тему удалили, создаём новую и шлём
    ещё раз. Второй неудачи достаточно, чтобы признать мост нерабочим и
    не спамить в лог на каждом событии мира.
    """
    if not await is_enabled():
        return None
    bot = bot or _bot()
    if bot is None or channel is None:
        return None

    chat_id = await get_chat_id()
    thread_id = await ensure_topic(session, channel, bot)
    if thread_id is None:
        return None

    for attempt in (1, 2):
        try:
            msg = await bot.send_message(
                chat_id=chat_id,
                message_thread_id=thread_id,
                text=text,
                parse_mode="HTML",
            )
            return msg.message_id
        except Exception as exc:
            if attempt == 2:
                logger.warning("community: отправка в %s не удалась: %s",
                               channel.key, exc)
                return None
            # Тему могли удалить — сбрасываем привязку и пробуем один раз.
            logger.info("community: тема %s недоступна (%s), пересоздаю",
                        channel.key, exc)
            await bind_thread(session, channel.key, chat_id, None)
            channel.thread_id = None
            thread_id = await ensure_topic(session, channel, bot)
            if thread_id is None:
                return None
    return None


async def announce(channel_key: str, text: str, bot=None) -> bool:
    """Событие игры → канал. Пишем в журнал ВСЕГДА, в Telegram — если можем.

    Порядок важен: сначала БД, потом Telegram. Иначе при выключенном мосте
    лента мира внутри игры оставалась бы пустой.
    """
    from core.community import get_channel

    async with async_session() as session:
        channel = await get_channel(session, channel_key)
        if channel is None:
            await ensure_default_channels(session)
            channel = await get_channel(session, channel_key)
        if channel is None:
            return False

        msg = await post_message(session, channel, text, source="game",
                                 is_system=True)
        tg_id = await send_to_channel(session, channel, text, bot)
        await attach_tg_id(session, msg, tg_id)
        await session.commit()
    return True


async def relay_from_game(character, channel_key: str, text: str,
                          bot=None) -> dict:
    """Игрок написал из бота → журнал + тема группы.

    Права проверяются здесь, а не в хендлере: точка входа может быть
    любой (личка бота, команда, панель), а правило одно.
    """
    from core.community import can_write, clean_text, get_channel

    body = clean_text(text)
    if not body:
        return {"ok": False, "reason": "Пустое сообщение."}

    async with async_session() as session:
        channel = await get_channel(session, channel_key)
        if channel is None:
            return {"ok": False, "reason": "Канал не найден."}
        if not await can_write(session, channel, character):
            if channel.access == ChannelAccess.READONLY.value:
                return {"ok": False,
                        "reason": "В этот канал пишет только игра."}
            return {"ok": False, "reason": "Нет доступа к этому каналу."}

        line = f"<b>{character.name}</b>: {body}"
        msg = await post_message(session, channel, body, character=character,
                                 source="bot")
        tg_id = await send_to_channel(session, channel, line, bot)
        await attach_tg_id(session, msg, tg_id)
        await session.commit()
        delivered = tg_id is not None
    return {"ok": True, "delivered": delivered, "channel": channel_key}


async def relay_from_telegram(message) -> dict | None:
    """Сообщение из темы группы → журнал игры.

    Возвращает None, если сообщение к сообществу не относится: чужой чат,
    не тема, служебное событие. Хендлер по None понимает, что реагировать
    не нужно.
    """
    from sqlalchemy import select

    from core.community import clean_text
    from core.models import Character, User

    chat_id = await get_chat_id()
    if not chat_id or str(message.chat.id) != str(chat_id):
        return None
    thread_id = getattr(message, "message_thread_id", None)
    if thread_id is None:
        return None
    body = clean_text(getattr(message, "text", "") or "")
    if not body:
        return None

    async with async_session() as session:
        channel = await by_thread(session, chat_id, thread_id)
        if channel is None:
            return None

        # Автор ищется по telegram_id: в игре у него есть персонаж, и
        # сообщение должно быть подписано игровым именем, а не ником TG.
        character = None
        tg_user = getattr(message, "from_user", None)
        if tg_user is not None:
            character = (await session.execute(
                select(Character).join(User)
                .where(User.telegram_id == tg_user.id)
            )).scalars().first()

        if character is None:
            # Пишет человек без персонажа — сохраняем под его ником TG.
            name = (getattr(tg_user, "full_name", "") or "Гость")[:64]
            msg = await post_message(session, channel, body, source="telegram",
                                     tg_message_id=message.message_id)
            if msg is not None:
                msg.author_name = name
        else:
            msg = await post_message(session, channel, body,
                                     character=character, source="telegram",
                                     tg_message_id=message.message_id)
        await session.commit()
        return {"channel": channel.key,
                "author": character.name if character else None}


async def setup_all_topics(bot=None) -> dict:
    """Создать темы под все активные каналы разом (кнопка в админке)."""
    async with async_session() as session:
        await ensure_default_channels(session)
        channels = await list_channels(session)
        created, skipped = [], []
        for ch in channels:
            if ch.thread_id:
                skipped.append(ch.key)
                continue
            thread_id = await ensure_topic(session, ch, bot)
            (created if thread_id else skipped).append(ch.key)
        await session.commit()
    return {"created": created, "skipped": skipped}
