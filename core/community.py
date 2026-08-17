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
    {"key": "tavern", "title": "Таверна", "icon": "🍺",
     "access": ChannelAccess.PUBLIC,
     "topic": "Оффтоп у очага: болтовня не по делу, шутки, знакомства."},
    {"key": "lore", "title": "Хроники", "icon": "📖",
     "access": ChannelAccess.PUBLIC,
     "topic": "Байки, отчёты о походах и сочинения о мире Теней."},
    {"key": "recruit", "title": "Набор в гильдии", "icon": "🏰",
     "access": ChannelAccess.PUBLIC,
     "topic": "Гильдии зовут новичков, вольные ищут дом."},
    {"key": "duels", "title": "Вызовы на дуэль", "icon": "🩸",
     "access": ChannelAccess.PUBLIC,
     "topic": "Кто кого: вызовы в Колизей и разбор поединков."},
]

MESSAGE_LIMIT = 2000          # длиннее Telegram всё равно не покажет одним куском
RECENT_DEFAULT = 30           # сколько сообщений отдаём по умолчанию
PAGE_DEFAULT = 12             # сообщений на странице истории

# Набор реакций намеренно закрытый: свободный ввод эмодзи превратил бы
# сводку под сообщением в кашу, а хранение — в свалку уникальных строк.
REACTIONS = ("👍", "🔥", "❤️", "😂", "🤝")

# Антифлуд. Считается по журналу в БД, без состояния в памяти: процесс
# бота перезапускается (кнопкой в панели), а ограничение должно пережить
# перезапуск — иначе рестарт превращается в способ обойти лимит.
#
# Порог намеренно щедрый. Задача — срезать пулемётную очередь, а не мешать
# живому разговору: в оживлённой перепалке десяток реплик за минуту это
# норма, и слишком строгий лимит бил бы по обычным игрокам, а не по
# спамерам. Дословные повторы ловятся отдельно и стоят дешевле.
RATE_WINDOW_SEC = 60          # окно наблюдения
RATE_MAX_IN_WINDOW = 12       # сколько сообщений в окне разрешено
REPEAT_WINDOW_SEC = 300       # за сколько секунд ловим дословный повтор


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
    # Закреп: одно сообщение на канал (см. `pin_message`). Держим флагом на
    # сообщении, а не ссылкой на канале, чтобы история закрепов не терялась
    # при мягком удалении и чтобы снятие закрепа было одной операцией.
    is_pinned = Column(Boolean, default=False)
    # Ответ на другое сообщение канала — из этого собираются ветки обсуждения.
    reply_to_id = Column(Integer, ForeignKey("community_messages.id"),
                         nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    channel = relationship("Channel", back_populates="messages")
    reactions = relationship("MessageReaction", back_populates="message",
                             cascade="all, delete-orphan")


class MessageReaction(Base):
    """Реакция героя на сообщение.

    UNIQUE(message, character, emoji) — повторный тап тем же эмодзи не
    плодит строки, а снимает реакцию (`toggle_reaction`).
    """
    __tablename__ = "community_reactions"
    __table_args__ = (
        UniqueConstraint("message_id", "character_id", "emoji",
                         name="uq_community_reaction"),
    )

    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, ForeignKey("community_messages.id"),
                        nullable=False, index=True)
    character_id = Column(Integer, ForeignKey("characters.id"),
                          nullable=False, index=True)
    emoji = Column(String(8), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    message = relationship("CommunityMessage", back_populates="reactions")


class ChannelSubscription(Base):
    """Подписка героя на канал + отметка о прочитанном.

    `last_read_message_id` двигается при открытии канала, из разницы с
    последним id считается счётчик непрочитанного. Хранить «непрочитано»
    числом нельзя: сообщения приходят из трёх источников (бот, группа,
    события мира), и любой пропущенный инкремент навсегда разъедется.
    """
    __tablename__ = "community_subscriptions"
    __table_args__ = (
        UniqueConstraint("channel_id", "character_id",
                         name="uq_community_subscription"),
    )

    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer, ForeignKey("community_channels.id"),
                        nullable=False, index=True)
    character_id = Column(Integer, ForeignKey("characters.id"),
                          nullable=False, index=True)
    # Подписка = «уведомляй меня». Отметка о прочитанном пишется всем, кто
    # заходил в канал, поэтому строка существует и при muted=True.
    muted = Column(Boolean, default=False)
    last_read_message_id = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


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


# Транслитерация для ключей каналов: ключ уходит в callback_data бота, где
# двоеточие — разделитель, а не-ASCII раздувает лимит в 64 байта.
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def slugify_key(raw: str) -> str:
    """Человеческое название → безопасный ключ канала.

    Кириллицу транслитерируем, а не выбрасываем: «Мои События 2026»
    должно стать `moi_sobytiya_2026`, а не голым `2026` — иначе ключ
    теряет смысл и превращается в мусор.
    """
    import re

    text = (raw or "").strip().lower()
    out = []
    for char in text:
        if char in _TRANSLIT:
            out.append(_TRANSLIT[char])
        elif char.isascii() and (char.isalnum() or char == "_"):
            out.append(char)
        else:
            out.append("_")
    key = re.sub(r"_+", "_", "".join(out)).strip("_")
    return key[:64]


async def post(session, channel: Channel, text: str, character=None,
               source: str = "game", tg_message_id=None,
               is_system: bool = False,
               reply_to_id: int | None = None) -> CommunityMessage | None:
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

    # Ответ засчитывается, только если отвечаем на сообщение ЭТОГО канала:
    # иначе ветка обсуждения могла бы указать в чужой закрытый канал и
    # утащить оттуда цитату.
    parent_id = None
    if reply_to_id:
        parent = await session.get(CommunityMessage, int(reply_to_id))
        if parent is not None and parent.channel_id == channel.id:
            parent_id = parent.id

    msg = CommunityMessage(
        channel_id=channel.id,
        author_character_id=getattr(character, "id", None),
        author_name=getattr(character, "name", "") or ("Мир" if is_system else ""),
        text=body,
        source=source,
        tg_message_id=int(tg_message_id) if tg_message_id is not None else None,
        is_system=is_system,
        reply_to_id=parent_id,
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


async def history_page(session, channel: Channel, page: int = 0,
                       per_page: int = PAGE_DEFAULT) -> dict:
    """Страница истории канала. page=0 — самые свежие сообщения.

    Листание идёт «вглубь»: нулевая страница всегда показывает конец
    разговора, как в мессенджере, а не начало времён.
    """
    if channel is None:
        return {"messages": [], "page": 0, "pages": 1, "total": 0,
                "has_older": False, "has_newer": False}

    per_page = max(1, min(int(per_page), 50))
    total = await session.scalar(
        select(func.count(CommunityMessage.id))
        .where(CommunityMessage.channel_id == channel.id)
        .where(CommunityMessage.is_deleted == False)  # noqa: E712
    ) or 0
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(int(page), pages - 1))

    rows = (await session.execute(
        select(CommunityMessage)
        .where(CommunityMessage.channel_id == channel.id)
        .where(CommunityMessage.is_deleted == False)  # noqa: E712
        .order_by(CommunityMessage.id.desc())
        .offset(page * per_page).limit(per_page)
    )).scalars().all()

    return {
        "messages": list(reversed(rows)),
        "page": page, "pages": pages, "total": total,
        "has_older": page + 1 < pages,
        "has_newer": page > 0,
    }


async def search(session, query: str, character=None, channel_key: str = "",
                 limit: int = 20) -> list:
    """Поиск по журналу. Возвращает пары (сообщение, канал).

    Права проверяются на каждый найденный канал: иначе поиск стал бы
    дырой, через которую видно закрытые каналы гильдий и фракций.
    """
    needle = (query or "").strip()
    if len(needle) < 2:
        return []

    q = (select(CommunityMessage)
         .where(CommunityMessage.is_deleted == False)  # noqa: E712
         .where(CommunityMessage.text.ilike(f"%{needle}%"))
         .order_by(CommunityMessage.id.desc())
         .limit(max(1, min(int(limit), 100)) * 3))
    if channel_key:
        ch = await get_channel(session, channel_key)
        if ch is None:
            return []
        q = q.where(CommunityMessage.channel_id == ch.id)

    found = (await session.execute(q)).scalars().all()

    out, allowed = [], {}
    for msg in found:
        ok = allowed.get(msg.channel_id)
        if ok is None:
            ch = await session.get(Channel, msg.channel_id)
            ok = await can_read(session, ch, character) if ch else False
            allowed[msg.channel_id] = ok
            if ok:
                allowed[f"obj_{msg.channel_id}"] = ch
        if not ok:
            continue
        out.append((msg, allowed.get(f"obj_{msg.channel_id}")))
        if len(out) >= limit:
            break
    return out


# ── реакции ─────────────────────────────────────────────────

async def toggle_reaction(session, message_id: int, character,
                          emoji: str) -> dict:
    """Поставить или снять реакцию. Повторный тап снимает её.

    Возвращает {"ok", "added", "counts"} — вызывающему нужно сразу
    перерисовать клавиатуру, поэтому счётчики отдаём здесь же.
    """
    if character is None:
        return {"ok": False, "reason": "Нужен герой.", "counts": {}}
    if emoji not in REACTIONS:
        return {"ok": False, "reason": "Неизвестная реакция.", "counts": {}}

    msg = await session.get(CommunityMessage, message_id)
    if msg is None or msg.is_deleted:
        return {"ok": False, "reason": "Сообщение не найдено.", "counts": {}}

    existing = (await session.execute(
        select(MessageReaction)
        .where(MessageReaction.message_id == message_id)
        .where(MessageReaction.character_id == character.id)
        .where(MessageReaction.emoji == emoji)
    )).scalar_one_or_none()

    if existing is not None:
        await session.delete(existing)
        added = False
    else:
        session.add(MessageReaction(message_id=message_id,
                                    character_id=character.id, emoji=emoji))
        added = True
    await session.flush()
    return {"ok": True, "added": added,
            "counts": await reaction_counts(session, message_id)}


async def reaction_counts(session, message_id: int) -> dict:
    """{эмодзи: сколько} для одного сообщения."""
    rows = (await session.execute(
        select(MessageReaction.emoji, func.count(MessageReaction.id))
        .where(MessageReaction.message_id == message_id)
        .group_by(MessageReaction.emoji)
    )).all()
    return {emoji: count for emoji, count in rows}


async def reactions_for(session, message_ids: list) -> dict:
    """Счётчики сразу для пачки сообщений — один запрос на экран.

    Поштучный `reaction_counts` в цикле давал бы N запросов на каждую
    отрисовку канала; экран открывают часто, поэтому агрегируем разом.
    """
    ids = [int(i) for i in message_ids if i]
    if not ids:
        return {}
    rows = (await session.execute(
        select(MessageReaction.message_id, MessageReaction.emoji,
               func.count(MessageReaction.id))
        .where(MessageReaction.message_id.in_(ids))
        .group_by(MessageReaction.message_id, MessageReaction.emoji)
    )).all()
    out = {}
    for mid, emoji, count in rows:
        out.setdefault(mid, {})[emoji] = count
    return out


# ── закреп ──────────────────────────────────────────────────

async def pin_message(session, message_id: int) -> CommunityMessage | None:
    """Закрепить сообщение, сняв предыдущий закреп канала.

    Закреп ровно один: «важное» перестаёт быть важным, когда его пять.
    """
    msg = await session.get(CommunityMessage, message_id)
    if msg is None or msg.is_deleted:
        return None
    old = (await session.execute(
        select(CommunityMessage)
        .where(CommunityMessage.channel_id == msg.channel_id)
        .where(CommunityMessage.is_pinned == True)  # noqa: E712
    )).scalars().all()
    for row in old:
        row.is_pinned = False
    msg.is_pinned = True
    await session.flush()
    return msg


async def unpin_channel(session, channel: Channel) -> bool:
    if channel is None:
        return False
    rows = (await session.execute(
        select(CommunityMessage)
        .where(CommunityMessage.channel_id == channel.id)
        .where(CommunityMessage.is_pinned == True)  # noqa: E712
    )).scalars().all()
    for row in rows:
        row.is_pinned = False
    await session.flush()
    return bool(rows)


async def pinned(session, channel: Channel) -> CommunityMessage | None:
    if channel is None:
        return None
    return (await session.execute(
        select(CommunityMessage)
        .where(CommunityMessage.channel_id == channel.id)
        .where(CommunityMessage.is_pinned == True)  # noqa: E712
        .where(CommunityMessage.is_deleted == False)  # noqa: E712
        .order_by(CommunityMessage.id.desc())
    )).scalars().first()


# ── подписки и непрочитанное ────────────────────────────────

async def _subscription(session, channel_id: int, character_id: int):
    return (await session.execute(
        select(ChannelSubscription)
        .where(ChannelSubscription.channel_id == channel_id)
        .where(ChannelSubscription.character_id == character_id)
    )).scalar_one_or_none()


async def toggle_mute(session, channel: Channel, character) -> bool:
    """Включить/выключить уведомления канала. Возвращает новое `muted`."""
    if channel is None or character is None:
        return False
    sub = await _subscription(session, channel.id, character.id)
    if sub is None:
        sub = ChannelSubscription(channel_id=channel.id,
                                  character_id=character.id, muted=True,
                                  last_read_message_id=0)
        session.add(sub)
        await session.flush()
        return True
    sub.muted = not bool(sub.muted)
    await session.flush()
    return bool(sub.muted)


async def is_muted(session, channel: Channel, character) -> bool:
    if channel is None or character is None:
        return False
    sub = await _subscription(session, channel.id, character.id)
    return bool(sub and sub.muted)


async def mark_read(session, channel: Channel, character) -> int:
    """Запомнить, что герой дочитал канал до последнего сообщения."""
    if channel is None or character is None:
        return 0
    last_id = await session.scalar(
        select(func.max(CommunityMessage.id))
        .where(CommunityMessage.channel_id == channel.id)
        .where(CommunityMessage.is_deleted == False)  # noqa: E712
    ) or 0
    sub = await _subscription(session, channel.id, character.id)
    if sub is None:
        session.add(ChannelSubscription(channel_id=channel.id,
                                        character_id=character.id,
                                        last_read_message_id=last_id))
    else:
        sub.last_read_message_id = max(int(sub.last_read_message_id or 0),
                                       int(last_id))
    await session.flush()
    return last_id


async def unread_counts(session, character, channels: list) -> dict:
    """{channel_id: сколько непрочитанного} для меню каналов.

    Собственные сообщения героя не считаются: иначе значок «новое»
    загорался бы от собственной реплики.
    """
    if character is None or not channels:
        return {}
    ids = [ch.id for ch in channels]

    subs = dict((await session.execute(
        select(ChannelSubscription.channel_id,
               ChannelSubscription.last_read_message_id)
        .where(ChannelSubscription.character_id == character.id)
        .where(ChannelSubscription.channel_id.in_(ids))
    )).all())

    # Один запрос на все каналы: считаем сообщения новее отметки о
    # прочитанном, чужие или системные. `id > last_read` работает, потому
    # что id монотонно растёт — по времени сравнивать нельзя, у системных
    # записей created_at ставит сервер БД.
    rows = (await session.execute(
        select(CommunityMessage.channel_id, CommunityMessage.id,
               CommunityMessage.author_character_id)
        .where(CommunityMessage.channel_id.in_(ids))
        .where(CommunityMessage.is_deleted == False)  # noqa: E712
    )).all()

    out = {}
    for channel_id, msg_id, author_id in rows:
        if author_id == character.id:
            continue
        if int(msg_id) <= int(subs.get(channel_id) or 0):
            continue
        out[channel_id] = out.get(channel_id, 0) + 1
    return out


async def subscribers(session, channel: Channel) -> list:
    """id героев, которым можно слать уведомление о новом сообщении.

    Возвращает только тех, кто канал не заглушил. Права здесь не
    проверяются — это делает вызывающий, у него уже есть сессия и канал.
    """
    if channel is None:
        return []
    rows = (await session.execute(
        select(ChannelSubscription.character_id)
        .where(ChannelSubscription.channel_id == channel.id)
        .where(ChannelSubscription.muted == False)  # noqa: E712
    )).scalars().all()
    return list(rows)


# ── антифлуд ────────────────────────────────────────────────

async def check_rate_limit(session, channel: Channel, character) -> dict:
    """Можно ли герою писать прямо сейчас.

    Два правила: не больше RATE_MAX_IN_WINDOW сообщений за минуту и
    никаких дословных повторов в течение REPEAT_WINDOW_SEC. Считаем по
    журналу, а не по счётчику в памяти: перезапуск бота не должен
    обнулять ограничение.
    """
    if character is None:
        return {"ok": False, "reason": "Нужен герой."}

    from datetime import timedelta

    since = _now() - timedelta(seconds=RATE_WINDOW_SEC)
    recent_count = await session.scalar(
        select(func.count(CommunityMessage.id))
        .where(CommunityMessage.author_character_id == character.id)
        .where(CommunityMessage.created_at >= since)
    ) or 0
    if recent_count >= RATE_MAX_IN_WINDOW:
        return {"ok": False,
                "reason": f"Слишком часто: не больше {RATE_MAX_IN_WINDOW} "
                          f"сообщений в минуту. Переведи дух."}
    return {"ok": True}


async def is_repeat(session, channel: Channel, character, text: str) -> bool:
    """Дословный повтор недавнего сообщения того же героя в том же канале."""
    if character is None or channel is None:
        return False

    from datetime import timedelta

    body = clean_text(text)
    if not body:
        return False
    since = _now() - timedelta(seconds=REPEAT_WINDOW_SEC)
    dup = (await session.execute(
        select(CommunityMessage.id)
        .where(CommunityMessage.channel_id == channel.id)
        .where(CommunityMessage.author_character_id == character.id)
        .where(CommunityMessage.text == body)
        .where(CommunityMessage.created_at >= since)
        .where(CommunityMessage.is_deleted == False)  # noqa: E712
    )).first()
    return dup is not None


# ── статистика сообщества ───────────────────────────────────

async def top_posters(session, limit: int = 5) -> list:
    """Самые активные авторы: (имя, сколько сообщений).

    Системные записи мира исключены — иначе «Мир» всегда был бы первым.
    """
    rows = (await session.execute(
        select(CommunityMessage.author_name,
               func.count(CommunityMessage.id).label("n"))
        .where(CommunityMessage.is_deleted == False)  # noqa: E712
        .where(CommunityMessage.is_system == False)  # noqa: E712
        .where(CommunityMessage.author_character_id.isnot(None))
        .group_by(CommunityMessage.author_name)
        .order_by(func.count(CommunityMessage.id).desc())
        .limit(max(1, min(int(limit), 20)))
    )).all()
    return [(name or "Кто-то", int(n)) for name, n in rows]


async def channel_activity(session, limit: int = 5) -> list:
    """Самые живые каналы: (канал, сколько сообщений)."""
    rows = (await session.execute(
        select(CommunityMessage.channel_id,
               func.count(CommunityMessage.id))
        .where(CommunityMessage.is_deleted == False)  # noqa: E712
        .group_by(CommunityMessage.channel_id)
        .order_by(func.count(CommunityMessage.id).desc())
        .limit(max(1, min(int(limit), 20)))
    )).all()
    out = []
    for channel_id, count in rows:
        ch = await session.get(Channel, channel_id)
        if ch is not None:
            out.append((ch, int(count)))
    return out


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
    reactions = await session.scalar(
        select(func.count(MessageReaction.id))
    ) or 0
    subs = await session.scalar(
        select(func.count(ChannelSubscription.id))
    ) or 0
    pins = await session.scalar(
        select(func.count(CommunityMessage.id))
        .where(CommunityMessage.is_pinned == True)  # noqa: E712
        .where(CommunityMessage.is_deleted == False)  # noqa: E712
    ) or 0
    return {"messages": total, "channels": channels, "linked": linked,
            "reactions": reactions, "subscriptions": subs, "pinned": pins}
