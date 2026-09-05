"""Сторона супергруппы: приём сообщений из тем и игровые команды в чате.

Этот роутер подключается ПОСЛЕДНИМ и работает только в группах
(`F.chat.type in {"group", "supergroup"}`), поэтому личке бота он не мешает.

Что делает:

* переносит реплики из привязанных тем в журнал игры — тогда заявка,
  написанная в «Поиске отряда», видна внутри бота;
* отвечает на игровые команды прямо в чате: профиль, гильдия, лоты
  аукциона, доска дуэлей.

Почему команды отвечают в теме, а не в личке: смысл структурированного
сообщества в том, что ответ видят все — «покажи профиль» превращается в
повод для разговора. Личные вещи (инвентарь, кошелёк) в чат не выводятся.
"""
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select

from core import community as C
from core.database import async_session
from core.models import Character, User

router = Router()
logger = logging.getLogger(__name__)

GROUP_TYPES = {"group", "supergroup"}

# Ограничение вывода: длинные простыни в общем чате читать невозможно.
LIST_LIMIT = 5


def _q(text) -> str:
    """Экран для HTML-ответов в чате: имена, тексты сообщений и цитаты
    игроков (а также названия, которые админ ввёл без санитайзера) вставляются
    в parse_mode="HTML" только после экранирования."""
    from html import escape

    return escape(str(text if text is not None else ""), quote=False)


async def _character(session, telegram_id: int):
    return (await session.execute(
        select(Character).join(User).where(User.telegram_id == telegram_id)
    )).scalars().first()


async def _require_character(message: Message):
    """Персонаж автора или None с уже отправленной подсказкой."""
    async with async_session() as session:
        character = await _character(session, message.from_user.id)
    if character is None:
        await message.reply(
            "У тебя ещё нет героя. Напиши боту в личку /start — "
            "и возвращайся.")
        return None
    return character


@router.message(Command("профиль", "profile"), F.chat.type.in_(GROUP_TYPES))
async def cmd_profile(message: Message):
    """Короткая витрина героя прямо в чате."""
    character = await _require_character(message)
    if character is None:
        return

    async with async_session() as session:
        from core import factions as core_factions
        from core import karma as core_karma
        from core import titles as core_titles

        char = await session.get(Character, character.id)
        icon, karma_title, _ = core_karma.karma_status(char)
        faction_key = core_factions.allegiance(char)
        faction = (core_factions.FACTIONS.get(faction_key) or ("", "вольный"))
        title = getattr(char, "active_title", None)
        unlocked = len(core_titles.get_unlocked_titles(char))

    lines = [
        f"🧙 <b>{_q(char.name)}</b> — {_q(char.character_class)}, ур. {char.level}",
        f"❤️ {char.current_hp}/{char.max_hp} · "
        f"💪 {char.strength} · 🏃 {char.agility} · 🧠 {char.intelligence}",
        f"{faction[0]} {faction[1]} · {icon} {karma_title}",
    ]
    if title:
        lines.append(f"🎖 {title} <i>(титулов открыто: {unlocked})</i>")
    if getattr(char, "rebirth_count", 0):
        lines.append(f"♻️ Кругов перерождения: {char.rebirth_count}")
    await message.reply("\n".join(lines), parse_mode="HTML")


@router.message(Command("гильдия", "guild"), F.chat.type.in_(GROUP_TYPES))
async def cmd_guild(message: Message):
    """Состояние гильдии автора: казна, уровень, состав."""
    character = await _require_character(message)
    if character is None:
        return

    async with async_session() as session:
        from core.guilds import Guild, guild_members

        guild_id = (await session.execute(
            select(guild_members.c.guild_id)
            .where(guild_members.c.character_id == character.id)
        )).scalars().first()
        if not guild_id:
            await message.reply(
                "Ты пока сам по себе. Гильдию можно основать в боте: "
                "меню → 🏛 Гильдия.")
            return
        guild = await session.get(Guild, guild_id)
        members = (await session.execute(
            select(Character.name, Character.level)
            .join(guild_members, guild_members.c.character_id == Character.id)
            .where(guild_members.c.guild_id == guild_id)
            .order_by(Character.level.desc())
        )).all()

    lines = [f"🏰 <b>{_q(guild.name)}</b> — уровень {guild.level or 1}",
             f"💰 Казна: {guild.treasury_bronze or 0}🟤 · "
             f"👥 Участников: {len(members)}"]
    for name, level in members[:LIST_LIMIT]:
        lines.append(f"   • {_q(name)} <i>(ур. {level})</i>")
    if len(members) > LIST_LIMIT:
        lines.append(f"   <i>…и ещё {len(members) - LIST_LIMIT}</i>")
    await message.reply("\n".join(lines), parse_mode="HTML")


@router.message(Command("аукцион", "auction"), F.chat.type.in_(GROUP_TYPES))
async def cmd_auction(message: Message):
    """Свежие лоты — самый частый повод зайти в «Торговую площадь»."""
    async with async_session() as session:
        from core.enums import AuctionStatus
        from core.models import AuctionLot, Item

        lots = (await session.execute(
            select(AuctionLot)
            .where(AuctionLot.status == AuctionStatus.ACTIVE)
            .order_by(AuctionLot.id.desc())
            .limit(LIST_LIMIT)
        )).scalars().all()
        rows = []
        for lot in lots:
            item = await session.get(Item, lot.item_id) if lot.item_id else None
            rows.append((item.name if item else "лот", lot.price))

    if not rows:
        await message.reply("⚖️ На аукционе сейчас пусто.")
        return
    lines = ["⚖️ <b>Свежие лоты</b>"]
    lines += [f"   • {_q(name)} — <b>{price}</b>🟤" for name, price in rows]
    lines.append("<i>Купить можно в боте: меню → ⚖️ Аукцион.</i>")
    await message.reply("\n".join(lines), parse_mode="HTML")


@router.message(Command("арена", "arena"), F.chat.type.in_(GROUP_TYPES))
async def cmd_arena(message: Message):
    """Топ Колизея и открытые вызовы на дуэль."""
    async with async_session() as session:
        from core.models import CharacterShadow

        top = (await session.execute(
            select(CharacterShadow)
            .order_by(CharacterShadow.arena_rating.desc())
            .limit(LIST_LIMIT)
        )).scalars().all()

    from bot.handlers import world_extra

    pending = world_extra.pending_duels()

    lines = ["🩸 <b>Колизей Теней</b>"]
    if top:
        for i, sh in enumerate(top, 1):
            lines.append(f"   {i}. {_q(sh.name)} — <b>{sh.arena_rating}</b> "
                         f"<i>(ур. {sh.level})</i>")
    else:
        lines.append("   <i>Теней пока нет — арена ждёт первого бойца.</i>")
    if pending:
        lines.append(f"⚔️ Открытых вызовов на дуэль: <b>{len(pending)}</b>")
    await message.reply("\n".join(lines), parse_mode="HTML")


@router.message(Command("каналы", "channels"), F.chat.type.in_(GROUP_TYPES))
async def cmd_channels(message: Message):
    """Карта сообщества: какие темы есть и о чём они."""
    async with async_session() as session:
        await C.ensure_default_channels(session)
        await session.commit()
        channels = await C.list_channels(session)

    lines = ["🗂 <b>Каналы сообщества</b>", ""]
    for ch in channels:
        mark = {C.ChannelAccess.READONLY.value: " <i>(только игра пишет)</i>",
                C.ChannelAccess.MEMBERS.value: " <i>(закрытый)</i>"}.get(
                    ch.access, "")
        lines.append(f"{_q(ch.label())}{mark}")
        if ch.topic:
            lines.append(f"   <i>{_q(ch.topic)}</i>")
    await message.reply("\n".join(lines), parse_mode="HTML")


@router.message(Command("топ", "top"), F.chat.type.in_(GROUP_TYPES))
async def cmd_top(message: Message):
    """Кто держит мир: сильнейшие герои по уровню."""
    async with async_session() as session:
        heroes = (await session.execute(
            select(Character.name, Character.level, Character.character_class)
            .order_by(Character.level.desc(), Character.experience.desc())
            .limit(LIST_LIMIT)
        )).all()

    if not heroes:
        await message.reply("🏆 Героев пока нет — мир ждёт первого.")
        return
    lines = ["🏆 <b>Сильнейшие герои</b>"]
    medals = ["🥇", "🥈", "🥉"]
    for i, (name, level, klass) in enumerate(heroes):
        mark = medals[i] if i < len(medals) else f"{i + 1}."
        lines.append(f"   {mark} {_q(name)} — ур. <b>{level}</b> <i>({klass})</i>")
    await message.reply("\n".join(lines), parse_mode="HTML")


@router.message(Command("сводка", "digest"), F.chat.type.in_(GROUP_TYPES))
async def cmd_digest(message: Message):
    """Пульс сообщества: сколько говорят и кто громче всех."""
    async with async_session() as session:
        info = await C.stats(session)
        top = await C.top_posters(session, LIST_LIMIT)
        activity = await C.channel_activity(session, 3)

    lines = ["📊 <b>Пульс сообщества</b>",
             f"Сообщений: <b>{info['messages']}</b> · "
             f"каналов: <b>{info['channels']}</b> · "
             f"реакций: <b>{info['reactions']}</b>", ""]
    if top:
        lines.append("🗣 <b>Самые говорливые</b>")
        for i, (name, count) in enumerate(top, 1):
            lines.append(f"   {i}. {_q(name)} — <b>{count}</b>")
    if activity:
        lines.append("🔥 <b>Живые каналы</b>")
        for ch, count in activity:
            lines.append(f"   {_q(ch.label())} — <b>{count}</b>")
    await message.reply("\n".join(lines), parse_mode="HTML")


@router.message(Command("закреп", "pinned"), F.chat.type.in_(GROUP_TYPES))
async def cmd_pinned(message: Message):
    """Что закреплено в канале этой темы.

    Работает только внутри привязанной темы: в общем чате группы
    непонятно, о каком канале речь.
    """
    thread_id = getattr(message, "message_thread_id", None)
    from bot import community_bridge as bridge

    chat_id = await bridge.get_chat_id()
    async with async_session() as session:
        channel = await C.by_thread(session, chat_id, thread_id) \
            if chat_id and thread_id else None
        if channel is None:
            await message.reply(
                "📌 Команда работает внутри темы канала сообщества.")
            return
        pin = await C.pinned(session, channel)

    if pin is None:
        await message.reply(f"📌 В {channel.label()} ничего не закреплено.")
        return
    who = pin.author_name or "Мир"
    body = pin.text if pin.is_system else _q(pin.text)
    await message.reply(f"📌 <b>Закреплено в {_q(channel.label())}</b>\n\n"
                        f"<b>{_q(who)}</b>: {body}", parse_mode="HTML")


@router.message(Command("поиск", "search"), F.chat.type.in_(GROUP_TYPES))
async def cmd_search(message: Message):
    """Поиск по журналу сообщества прямо из чата."""
    parts = (message.text or "").split(maxsplit=1)
    query = parts[1].strip() if len(parts) > 1 else ""
    if len(query) < 2:
        await message.reply(
            "🔎 Что искать? Например: <code>/поиск подземелье</code>",
            parse_mode="HTML")
        return

    character = await _require_character(message)
    if character is None:
        return

    async with async_session() as session:
        results = await C.search(session, query, character=character,
                                 limit=LIST_LIMIT)

    if not results:
        await message.reply(f"🔎 По запросу «{query}» ничего не нашлось.")
        return
    lines = [f"🔎 <b>Найдено по «{_q(query)}»</b>"]
    for msg, channel in results:
        who = msg.author_name or ("Мир" if msg.is_system else "Кто-то")
        body = " ".join((msg.text or "").split())
        if len(body) > 70:
            body = body[:69] + "…"
        body = _q(body) if not msg.is_system else body
        label = channel.label() if channel is not None else "канал"
        lines.append(f"   {_q(label)} · <b>{_q(who)}</b>: <i>{body}</i>")
    await message.reply("\n".join(lines), parse_mode="HTML")


@router.message(Command("помощь", "help"), F.chat.type.in_(GROUP_TYPES))
async def cmd_help(message: Message):
    await message.reply(
        "🕯 <b>Команды в чате</b>\n\n"
        "/профиль — твой герой\n"
        "/гильдия — казна и состав\n"
        "/аукцион — свежие лоты\n"
        "/арена — топ Колизея и вызовы\n"
        "/топ — сильнейшие герои\n"
        "/каналы — карта сообщества\n"
        "/сводка — пульс сообщества\n"
        "/закреп — что закреплено в этой теме\n"
        "/поиск &lt;слово&gt; — найти в журнале\n\n"
        "<i>Всё остальное — в личке бота.</i>",
        parse_mode="HTML")


@router.message(F.chat.type.in_(GROUP_TYPES), F.text)
async def relay_group_message(message: Message):
    """Реплика из темы → журнал канала.

    Стоит последним и ничего не отвечает: если тема не привязана к каналу,
    мост вернёт None и сообщение просто останется в Telegram. Молчание тут
    осознанное — бот не должен комментировать каждую фразу в чате.
    """
    from bot import community_bridge as bridge

    try:
        await bridge.relay_from_telegram(message)
    except Exception as exc:
        logger.debug("community: приём из группы не удался: %s", exc)
