"""Структурированное сообщество: каналы, участники, сообщения.

Зачем это ядро отдельно от Telegram. Чат живёт в супергруппе с форум-темами
(каждая тема = канал), но сам Telegram — **транспорт**, а не источник правды:

* доступ к гильдейскому каналу определяется членством в `core/guilds.py`,
  а не тем, кого админ вручную добавил в тему;
* сообщения нужны игре (заявка в «Поиск отряда» видна внутри бота), а из
  Telegram их задним числом не вычитать: Bot API не отдаёт историю чата;
* топик могут удалить или пересоздать — привязка `thread_id` обязана
  переживать это без потери канала.

Поэтому здесь: каталог каналов, правила доступа и журнал сообщений. Мост в
Telegram — `bot/community_bridge.py`, он ничего не решает сам, только носит.

Каналы бывают трёх видов (`ChannelKind`):
  fixed  — заводятся из `DEFAULT_CHANNELS` при первом запуске;
  guild  — по одному на гильдию, доступ = членство в ней;
  faction— по одному на каждую из четырёх сил (`core/factions.ORDER`),
           доступ = присяга герою этой фракции.

Каналы гильдий и фракций **не создаются заранее пачкой**: они появляются
по требованию (`ensure_guild_channel` / `ensure_faction_channel`), иначе в
списке висели бы десятки пустых тем.
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer,
                        String, Text, UniqueConstraint, func, select)
from sqlalchemy.orm import relationship

from core.database import Base


class ChannelKind(str, enum.Enum):
    FIXED = "fixed"
    GUILD = "guild"
    FACTION = "faction"


class ChannelAccess(str, enum.Enum):
    """Кто может читать и писать."""
    PUBLIC = "public"        # все игроки
    MEMBERS = "members"      # только участники (гильдия/фракция)
    READONLY = "readonly"    # пишет только игра; игроки читают


# Стартовый набор. Порядок = порядок тем в группе и в меню бота.
DEFAULT_CHANNELS = [
    {"key": "general", "title": "Общий зал", "icon": "🏛",
     "access": ChannelAccess.PUBLIC,
     "topic": "Общение обо всём: знакомства, вопросы, байки у костра."},
    {"key": "trade", "title": "Торговая площадь", "icon": "🪙",
     "access": ChannelAccess.PUBLIC,
     "topic": "Куплю-продам, обмен, лоты аукциона."},
    {"key": "lfg", "title": "Поиск отряда", "icon": "🤝",
     "access": ChannelAccess.PUBLIC,
     "topic": "Ищу спутников в подземелье, на босса, в вылазку."},
    {"key": "world", "title": "Лента мира", "icon": "📜",
     "access": ChannelAccess.READONLY,
     "topic": "Катаклизмы, боссы, порталы и рекорды. Пишет только игра."},
    {"key": "newbies", "title": "Помощь новичкам", "icon": "🕯",
     "access": ChannelAccess.PUBLIC,
     "topic": "Спрашивай, не стесняйся: тут отвечают на глупые вопросы."},
]

MESSAGE_LIMIT = 2000          # длиннее Telegram всё равно не покажет одним куском
RECENT_DEFAULT = 30           # сколько сообщений отдаём по умолчанию


class Channel(Base):
    """Канал сообщества. `thread_id` — тема в супергруппе (может быть пуст)."""
    __tablename__ = "community_channels"

    id = Column(Integer, primary_key=True)
    key = Column(String(64), unique=True, nullable=False, index=True)
    title = Column(String(96), nullable=False)
    icon = Column(String(8), default="💬")
    topic = Column(Text, default="")
    kind = Column(String(16), default=ChannelKind.FIXED.value)
    access = Column(String(16), default=ChannelAccess.PUBLIC.value)

    # Привязка к Telegram. Пустой thread_id — канал есть в игре, но темы
    # в группе ещё нет (группа не настроена или тему удалили).
    chat_id = Column(String(32), default="")
    thread_id = Column(Integer, nullable=True)

    # Для guild/faction — на кого канал завязан.
    guild_id = Column(Integer, nullable=True, index=True)
    faction_key = Column(String(32), nullable=True, index=True)

    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=100)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    messages = relationship("CommunityMessage", back_populates="channel",
                            cascade="all, delete-orphan")

    def label(self) -> str:
        return f"{self.icon or '💬'} {self.title}"


class CommunityMessage(Base):
    """Сообщение канала.

    `author_character_id` пуст у системных сообщений (события мира).
    `tg_message_id` нужен, чтобы не завести дубль, когда мост получает
    эхо собственной отправки.
    """
    __tablename__ = "community_messages"
    __table_args__ = (
        UniqueConstraint("channel_id", "tg_message_id",
                         name="uq_community_msg_tg"),
    )

    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer, ForeignKey("community_channels.id"),
                        nullable=False, index=True)
    author_character_id = Column(Integer, ForeignKey("characters.id"),
                                 nullable=True, index=True)
    author_name = Column(String(64), default="")
    text = Column(Text, nullable=False)

    # Откуда пришло: "bot" (личка бота), "telegram" (тема группы),
    # "game" (событие мира), "admin" (панель).
    source = Column(String(16), default="game")
    tg_message_id = Column(Integer, nullable=True)
    is_system = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    channel = relationship("Channel", back_populates="messages")


def _now():
    return datetime.now(timezone.utc)


# ── каталог каналов ─────────────────────────────────────────

async def get_channel(session, key: str) -> Channel | None:
    return (await session.execute(
        select(Channel).where(Channel.key == key)
    )).scalar_one_or_none()


async def by_thread(session, chat_id, thread_id) -> Channel | None:
    """Найти канал по теме Telegram — точка входа моста «из группы в игру»."""
    if thread_id is None:
        return None
    return (await session.execute(
        select(Channel)
        .where(Channel.chat_id == str(chat_id))
        .where(Channel.thread_id == int(thread_id))
    )).scalar_one_or_none()


async def list_channels(session, kind: str | None = None,
                        active_only: bool = True) -> list:
    q = select(Channel)
    if kind:
        q = q.where(Channel.kind == kind)
    if active_only:
        q = q.where(Channel.is_active == True)  # noqa: E712
    q = q.order_by(Channel.sort_order, Channel.id)
    return (await session.execute(q)).scalars().all()


async def ensure_default_channels(session) -> list:
    """Завести фиксированные каналы. Идемпотентно: повтор ничего не портит."""
    created = []
    for order, spec in enumerate(DEFAULT_CHANNELS):
        existing = await get_channel(session, spec["key"])
        if existing is not None:
            continue
        ch = Channel(
            key=spec["key"], title=spec["title"], icon=spec["icon"],
            topic=spec["topic"], kind=ChannelKind.FIXED.value,
            access=spec["access"].value, sort_order=order,
        )
        session.add(ch)
        created.append(ch)
    await session.flush()
    return created


async def ensure_guild_channel(session, guild) -> Channel:
    """Канал гильдии. Создаётся при первом обращении, а не пачкой."""
    key = f"guild_{guild.id}"
    ch = await get_channel(session, key)
    if ch is None:
        ch = Channel(
            key=key, title=guild.name, icon="🏰",
            topic=f"Закрытый канал гильдии «{guild.name}».",
            kind=ChannelKind.GUILD.value,
            access=ChannelAccess.MEMBERS.value,
            guild_id=guild.id, sort_order=500,
        )
        session.add(ch)
        await session.flush()
    elif ch.title != guild.name:
        # Гильдию переименовали — канал не должен жить под старым именем.
        ch.title = guild.name
        ch.topic = f"Закрытый канал гильдии «{guild.name}»."
    return ch


async def ensure_faction_channel(session, faction_key: str) -> Channel | None:
    """Канал фракции. Значок и название берутся из core/factions."""
    from core import factions as core_factions

    row = core_factions.FACTIONS.get(faction_key)
    if row is None:
        return None
    icon, name = row[0], row[1]
    key = f"faction_{faction_key}"
    ch = await get_channel(session, key)
    if ch is None:
        ch = Channel(
            key=key, title=name, icon=icon,
            topic=f"Канал силы «{name}». Только для присягнувших.",
            kind=ChannelKind.FACTION.value,
            access=ChannelAccess.MEMBERS.value,
            faction_key=faction_key,
            sort_order=300 + core_factions.ORDER.index(faction_key),
        )
        session.add(ch)
        await session.flush()
    return ch


async def bind_thread(session, key: str, chat_id, thread_id) -> Channel | None:
    """Привязать канал к теме супергруппы (делает мост после создания темы)."""
    ch = await get_channel(session, key)
    if ch is None:
        return None
    ch.chat_id = str(chat_id)
    ch.thread_id = int(thread_id) if thread_id is not None else None
    await session.flush()
    return ch


# ── доступ ──────────────────────────────────────────────────

async def can_read(session, channel: Channel, character) -> bool:
    """Может ли герой читать канал.

    Правило одно для бота, группы и панели: членство проверяется по игре,
    а не по составу темы в Telegram.
    """
    if channel is None or not channel.is_active:
        return False
    if channel.access == ChannelAccess.PUBLIC.value:
        return True
    if channel.access == ChannelAccess.READONLY.value:
        return True
    if character is None:
        return False

    if channel.kind == ChannelKind.GUILD.value:
        from core.guilds import guild_members

        row = (await session.execute(
            select(guild_members.c.character_id)
            .where(guild_members.c.guild_id == channel.guild_id)
            .where(guild_members.c.character_id == character.id)
        )).first()
        return row is not None

    if channel.kind == ChannelKind.FACTION.value:
        from core import factions as core_factions

        return core_factions.allegiance(character) == channel.faction_key

    return False


async def can_write(session, channel: Channel, character) -> bool:
    """Писать может тот, кто читает, кроме каналов «только для игры»."""
    if channel is not None and channel.access == ChannelAccess.READONLY.value:
        return False
    if character is None:
        return False
    return await can_read(session, channel, character)


async def visible_channels(session, character) -> list:
    """Каналы, которые герой вправе видеть — меню чата в боте."""
    out = []
    for ch in await list_channels(session):
        if await can_read(session, ch, character):
            out.append(ch)
    return out


# ── сообщения ───────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Обрезать и подчистить. Пустая строка = сообщения нет."""
    return (text or "").strip()[:MESSAGE_LIMIT]


async def post(session, channel: Channel, text: str, character=None,
               source: str = "game", tg_message_id=None,
               is_system: bool = False) -> CommunityMessage | None:
    """Записать сообщение в журнал канала.

    Дубли по `tg_message_id` отсекаются здесь, а не в мосте: эхо приходит и
    от группы, и от бота, а точка записи одна.
    """
    body = clean_text(text)
    if not body or channel is None:
        return None

    if tg_message_id is not None:
        dup = (await session.execute(
            select(CommunityMessage)
            .where(CommunityMessage.channel_id == channel.id)
            .where(CommunityMessage.tg_message_id == int(tg_message_id))
        )).scalar_one_or_none()
        if dup is not None:
            return dup

    msg = CommunityMessage(
        channel_id=channel.id,
        author_character_id=getattr(character, "id", None),
        author_name=getattr(character, "name", "") or ("Мир" if is_system else ""),
        text=body,
        source=source,
        tg_message_id=int(tg_message_id) if tg_message_id is not None else None,
        is_system=is_system,
    )
    session.add(msg)
    await session.flush()
    return msg


async def attach_tg_id(session, message, tg_message_id) -> bool:
    """Проставить id сообщения Telegram уже записанной строке.

    Отдельная функция, а не `msg.tg_message_id = ...`, из-за гонки: пока
    мост ждёт ответ Telegram, эхо того же сообщения может прийти из группы
    и создать строку с этим `tg_message_id`. Прямое присваивание тогда
    падало на UNIQUE и роняло отправку целиком — хотя сообщение уже
    доставлено и записано. Здесь конфликт не ошибка, а признак того, что
    строку успели завести: молча выходим.
    """
    if message is None or tg_message_id is None:
        return False
    tg_message_id = int(tg_message_id)

    taken = (await session.execute(
        select(CommunityMessage)
        .where(CommunityMessage.channel_id == message.channel_id)
        .where(CommunityMessage.tg_message_id == tg_message_id)
    )).scalar_one_or_none()
    if taken is not None:
        return taken.id == message.id

    message.tg_message_id = tg_message_id
    await session.flush()
    return True


async def recent(session, channel: Channel, limit: int = RECENT_DEFAULT) -> list:
    """Последние сообщения канала — в хронологическом порядке."""
    if channel is None:
        return []
    rows = (await session.execute(
        select(CommunityMessage)
        .where(CommunityMessage.channel_id == channel.id)
        .where(CommunityMessage.is_deleted == False)  # noqa: E712
        .order_by(CommunityMessage.id.desc())
        .limit(max(1, min(int(limit), 200)))
    )).scalars().all()
    return list(reversed(rows))


async def delete_message(session, message_id: int) -> bool:
    """Мягкое удаление: строка остаётся для истории модерации."""
    msg = await session.get(CommunityMessage, message_id)
    if msg is None or msg.is_deleted:
        return False
    msg.is_deleted = True
    await session.flush()
    return True


async def stats(session) -> dict:
    """Счётчики для админки."""
    total = await session.scalar(
        select(func.count(CommunityMessage.id))
        .where(CommunityMessage.is_deleted == False)  # noqa: E712
    ) or 0
    channels = await session.scalar(select(func.count(Channel.id))) or 0
    linked = await session.scalar(
        select(func.count(Channel.id)).where(Channel.thread_id.isnot(None))
    ) or 0
    return {"messages": total, "channels": channels, "linked": linked}
