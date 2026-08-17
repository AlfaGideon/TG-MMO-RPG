"""Чат сообщества внутри бота: каналы, чтение, отправка, реакции, поиск.

Экраны для игрока, который не хочет уходить в группу: он видит те же
каналы и те же сообщения, а мост (`bot/community_bridge.py`) доставляет
его реплику в тему супергруппы.

Права нигде здесь не считаются — за них отвечает `core/community.py`.
Гильдейский канал виден участнику гильдии, канал фракции — присягнувшему,
и это одно правило для бота, группы и админки.

Что умеет экран канала помимо чтения и отправки:

* **страницы истории** — канал не обрывается на последних 12 репликах;
* **ответы (ветки)** — реплика цитирует ту, на которую отвечает;
* **реакции** — закрытый набор из `core.community.REACTIONS`;
* **закреп** — одно важное сообщение всегда наверху экрана;
* **непрочитанное** — в списке каналов видно, где что-то новое;
* **тишина** — канал можно заглушить, чтобы не получать уведомления;
* **поиск** — по журналу с учётом прав на закрытые каналы.
"""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from bot.keyboards.inline import continue_keyboard
from bot.utils.edit import safe_edit_text
from core import community as C
from core.database import async_session
from core.models import Character, User

router = Router()

PAGE_SIZE = 12          # сообщений на экране: больше не влезает в одно окно
SNIPPET = 60            # длина цитаты в ветке и в результатах поиска


class ChatForm(StatesGroup):
    """Игрок пишет в канал. Ключ канала лежит в data, а не в имени состояния."""
    waiting_for_text = State()
    waiting_for_search = State()


async def _character(session, telegram_id: int):
    return (await session.execute(
        select(Character).join(User).where(User.telegram_id == telegram_id)
    )).scalar_one_or_none()


async def _sync_personal_channels(session, character):
    """Завести каналы гильдии и фракции героя, если их ещё нет.

    Ленивое создание: канал появляется у того, кому он положен, в момент
    захода в чат. Иначе пришлось бы заводить ветку каждой гильдии заранее.
    """
    from core import factions as core_factions
    from core.guilds import Guild, guild_members

    guild_id = (await session.execute(
        select(guild_members.c.guild_id)
        .where(guild_members.c.character_id == character.id)
    )).scalars().first()
    if guild_id:
        guild = await session.get(Guild, guild_id)
        if guild is not None:
            await C.ensure_guild_channel(session, guild)

    faction = core_factions.allegiance(character)
    if faction:
        await C.ensure_faction_channel(session, faction)


def _shorten(text: str, limit: int = SNIPPET) -> str:
    body = " ".join((text or "").split())
    return body if len(body) <= limit else body[:limit - 1] + "…"


def _channels_keyboard(channels, unread: dict):
    builder = InlineKeyboardBuilder()
    for ch in channels:
        count = unread.get(ch.id, 0)
        mark = f" ({count})" if count else ""
        builder.button(text=f"{ch.label()}{mark}",
                       callback_data=f"chat_open:{ch.key}")
    builder.button(text="🔎 Поиск", callback_data="chat_search")
    builder.button(text="📊 Сводка", callback_data="chat_digest")
    builder.button(text="◀️ Меню", callback_data="main_menu")
    builder.adjust(1, 1, 1)
    return builder.as_markup()


@router.callback_query(F.data == "chat_menu")
async def chat_menu(callback: CallbackQuery):
    """💬 Список каналов, доступных этому герою."""
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if character is None:
            await callback.answer("Сначала создай героя.", show_alert=True)
            return
        await C.ensure_default_channels(session)
        await _sync_personal_channels(session, character)
        await session.commit()
        channels = await C.visible_channels(session, character)
        unread = await C.unread_counts(session, character, channels)
        info = await C.stats(session)

    lines = ["💬 <b>Сообщество</b>", "",
             "<i>Каналы — как разделы на форуме: у каждого своя тема.</i>", ""]
    for ch in channels:
        mark = ""
        if ch.access == C.ChannelAccess.READONLY.value:
            mark = " <i>(только чтение)</i>"
        elif ch.access == C.ChannelAccess.MEMBERS.value:
            mark = " <i>(закрытый)</i>"
        count = unread.get(ch.id, 0)
        badge = f" — <b>{count} новых</b>" if count else ""
        lines.append(f"{ch.label()}{mark}{badge}")
        if ch.topic:
            lines.append(f"   <i>{ch.topic}</i>")
    if not channels:
        lines.append("<i>Пока ни одного канала. Загляни позже.</i>")
    total_new = sum(unread.values())
    tail = f" · непрочитанных: {total_new}" if total_new else ""
    lines += ["", f"<i>Всего сообщений в сообществе: {info['messages']}{tail}.</i>"]

    await safe_edit_text(callback, "\n".join(lines),
                         reply_markup=_channels_keyboard(channels, unread),
                         parse_mode="HTML")


def _render_message(m, reactions: dict, parents: dict) -> list:
    """Одно сообщение: цитата ответа, текст, сводка реакций."""
    out = []
    parent = parents.get(m.reply_to_id) if m.reply_to_id else None
    if parent is not None:
        who = parent.author_name or "Кто-то"
        out.append(f"   ↪️ <i>{who}: {_shorten(parent.text)}</i>")
    if m.is_system:
        out.append(f"📜 <i>{m.text}</i>")
    else:
        who = m.author_name or "Кто-то"
        pin = "📌 " if m.is_pinned else ""
        out.append(f"{pin}<b>{who}</b>: {m.text}")
    counts = reactions.get(m.id) or {}
    if counts:
        out.append("   " + "  ".join(f"{e} {n}" for e, n in counts.items()))
    return out


async def _render_channel(callback, key: str, page: int = 0):
    """Экран канала: закреп, страница истории, кнопки действий."""
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        channel = await C.get_channel(session, key)
        if channel is None:
            await callback.answer("Канал не найден.", show_alert=True)
            return
        if not await C.can_read(session, channel, character):
            await callback.answer("У тебя нет доступа к этому каналу.",
                                  show_alert=True)
            return

        page_data = await C.history_page(session, channel, page, PAGE_SIZE)
        messages = page_data["messages"]
        writable = await C.can_write(session, channel, character)
        pin = await C.pinned(session, channel)
        muted = await C.is_muted(session, channel, character)
        reactions = await C.reactions_for(session, [m.id for m in messages])

        # Родители для веток — одним проходом, без запроса на сообщение.
        parents = {}
        for m in messages:
            if m.reply_to_id and m.reply_to_id not in parents:
                parents[m.reply_to_id] = await session.get(
                    C.CommunityMessage, m.reply_to_id)

        # Отметку о прочитанном двигаем только на свежей странице: уход
        # в глубь истории не должен гасить значок «новое».
        if page == 0 and character is not None:
            await C.mark_read(session, channel, character)
            await session.commit()

        last_id = messages[-1].id if messages else 0

    lines = [f"{channel.label()}"]
    if page_data["pages"] > 1:
        lines[0] += f"  <i>(стр. {page_data['page'] + 1}/{page_data['pages']})</i>"
    lines.append("")
    if channel.topic:
        lines += [f"<i>{channel.topic}</i>", ""]
    if pin is not None and page == 0:
        lines += [f"📌 <b>Закреплено:</b> <i>{_shorten(pin.text, 120)}</i>", ""]
    if not messages:
        lines.append("<i>Здесь ещё тихо. Скажи первое слово.</i>")
    for m in messages:
        lines += _render_message(m, reactions, parents)

    builder = InlineKeyboardBuilder()
    if writable:
        builder.button(text="✍️ Написать", callback_data=f"chat_write:{key}")
        if last_id:
            builder.button(text="↪️ Ответить",
                           callback_data=f"chat_reply:{key}:{last_id}")
    if last_id:
        builder.button(text="😀 Реакция",
                       callback_data=f"chat_react:{key}:{last_id}:{page}")
    nav = []
    if page_data["has_older"]:
        nav.append(("⬅️ Раньше", f"chat_page:{key}:{page + 1}"))
    if page_data["has_newer"]:
        nav.append(("Позже ➡️", f"chat_page:{key}:{page - 1}"))
    for text, data in nav:
        builder.button(text=text, callback_data=data)
    builder.button(text="🔔 Уведомления: выкл" if muted else "🔕 Заглушить",
                   callback_data=f"chat_mute:{key}:{page}")
    builder.button(text="🔄 Обновить", callback_data=f"chat_page:{key}:{page}")
    builder.button(text="◀️ К каналам", callback_data="chat_menu")
    builder.adjust(2, 1, 2, 1, 1, 1)

    await safe_edit_text(callback, "\n".join(lines),
                         reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("chat_open:"))
async def chat_open(callback: CallbackQuery):
    """Показать последние сообщения канала."""
    await _render_channel(callback, callback.data.split(":", 1)[1], 0)


@router.callback_query(F.data.startswith("chat_page:"))
async def chat_page(callback: CallbackQuery):
    """Листание истории канала."""
    _, key, page = callback.data.split(":", 2)
    try:
        page_num = max(0, int(page))
    except ValueError:
        page_num = 0
    await _render_channel(callback, key, page_num)


@router.callback_query(F.data.startswith("chat_mute:"))
async def chat_mute(callback: CallbackQuery):
    """Заглушить канал или вернуть уведомления."""
    _, key, page = callback.data.split(":", 2)
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        channel = await C.get_channel(session, key)
        if channel is None or character is None:
            await callback.answer("Канал не найден.", show_alert=True)
            return
        muted = await C.toggle_mute(session, channel, character)
        await session.commit()
    await callback.answer("🔕 Канал заглушён." if muted
                          else "🔔 Уведомления включены.")
    await _render_channel(callback, key, int(page or 0))


@router.callback_query(F.data.startswith("chat_react:"))
async def chat_react(callback: CallbackQuery):
    """Выбор реакции на сообщение."""
    _, key, message_id, page = callback.data.split(":", 3)

    builder = InlineKeyboardBuilder()
    for emoji in C.REACTIONS:
        builder.button(text=emoji,
                       callback_data=f"chat_react_do:{key}:{message_id}:{emoji}:{page}")
    builder.button(text="◀️ Назад", callback_data=f"chat_page:{key}:{page}")
    builder.adjust(len(C.REACTIONS), 1)

    await safe_edit_text(
        callback,
        "😀 <b>Выбери реакцию</b>\n\n"
        "<i>Повторный тап той же реакцией снимает её.</i>",
        reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("chat_react_do:"))
async def chat_react_do(callback: CallbackQuery):
    """Поставить или снять реакцию."""
    _, key, message_id, emoji, page = callback.data.split(":", 4)

    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if character is None:
            await callback.answer("Сначала создай героя.", show_alert=True)
            return
        channel = await C.get_channel(session, key)
        if channel is None or not await C.can_read(session, channel, character):
            await callback.answer("Нет доступа.", show_alert=True)
            return
        result = await C.toggle_reaction(session, int(message_id), character,
                                         emoji)
        await session.commit()

    if not result.get("ok"):
        await callback.answer(result.get("reason", "Не вышло."),
                              show_alert=True)
        return
    await callback.answer(f"{emoji} поставлено" if result["added"]
                          else f"{emoji} снято")
    await _render_channel(callback, key, int(page or 0))


@router.callback_query(F.data.startswith("chat_write:"))
async def chat_write(callback: CallbackQuery, state: FSMContext):
    """Перевести бота в режим ввода сообщения для канала."""
    key = callback.data.split(":", 1)[1]

    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        channel = await C.get_channel(session, key)
        if channel is None or not await C.can_write(session, channel, character):
            await callback.answer("Сюда писать нельзя.", show_alert=True)
            return
        label = channel.label()

    await state.set_state(ChatForm.waiting_for_text)
    await state.update_data(chat_channel=key, chat_reply_to=None)

    builder = InlineKeyboardBuilder()
    builder.button(text="✖️ Отмена", callback_data=f"chat_cancel:{key}")
    await safe_edit_text(
        callback,
        f"✍️ <b>Сообщение в {label}</b>\n\n"
        f"Напиши текст одним сообщением — оно уйдёт в канал и в группу "
        f"сообщества.\n\n<i>Максимум {C.MESSAGE_LIMIT} символов.</i>",
        reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("chat_reply:"))
async def chat_reply(callback: CallbackQuery, state: FSMContext):
    """Ответить на конкретное сообщение — так собираются ветки."""
    _, key, message_id = callback.data.split(":", 2)

    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        channel = await C.get_channel(session, key)
        if channel is None or not await C.can_write(session, channel, character):
            await callback.answer("Сюда писать нельзя.", show_alert=True)
            return
        parent = await session.get(C.CommunityMessage, int(message_id))
        if parent is None or parent.channel_id != channel.id:
            await callback.answer("Сообщение не найдено.", show_alert=True)
            return
        quote = f"{parent.author_name or 'Кто-то'}: {_shorten(parent.text)}"

    await state.set_state(ChatForm.waiting_for_text)
    await state.update_data(chat_channel=key, chat_reply_to=int(message_id))

    builder = InlineKeyboardBuilder()
    builder.button(text="✖️ Отмена", callback_data=f"chat_cancel:{key}")
    await safe_edit_text(
        callback,
        f"↪️ <b>Ответ</b>\n\n<i>{quote}</i>\n\nНапиши текст одним сообщением.",
        reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("chat_cancel:"))
async def chat_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await _render_channel(callback, callback.data.split(":", 1)[1], 0)


@router.callback_query(F.data == "chat_search")
async def chat_search(callback: CallbackQuery, state: FSMContext):
    """Поиск по журналу сообщества."""
    await state.set_state(ChatForm.waiting_for_search)

    builder = InlineKeyboardBuilder()
    builder.button(text="✖️ Отмена", callback_data="chat_menu")
    await safe_edit_text(
        callback,
        "🔎 <b>Поиск по сообществу</b>\n\n"
        "Напиши, что искать — покажу свежие совпадения.\n\n"
        "<i>Ищет только в каналах, которые тебе доступны.</i>",
        reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "chat_digest")
async def chat_digest(callback: CallbackQuery):
    """Сводка: кто активнее всех и где кипит жизнь."""
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if character is None:
            await callback.answer("Сначала создай героя.", show_alert=True)
            return
        info = await C.stats(session)
        top = await C.top_posters(session, 5)
        activity = await C.channel_activity(session, 5)
        channels = await C.visible_channels(session, character)
        unread = await C.unread_counts(session, character, channels)
        visible = {ch.id for ch in channels}

    lines = ["📊 <b>Сводка сообщества</b>", "",
             f"Сообщений: <b>{info['messages']}</b> · "
             f"каналов: <b>{info['channels']}</b> · "
             f"реакций: <b>{info['reactions']}</b>", ""]

    lines.append("🗣 <b>Самые говорливые</b>")
    if top:
        for i, (name, count) in enumerate(top, 1):
            lines.append(f"   {i}. {name} — <b>{count}</b>")
    else:
        lines.append("   <i>Пока тихо.</i>")

    lines += ["", "🔥 <b>Где кипит жизнь</b>"]
    shown = [(ch, n) for ch, n in activity if ch.id in visible]
    if shown:
        for ch, count in shown:
            lines.append(f"   {ch.label()} — <b>{count}</b>")
    else:
        lines.append("   <i>Пока тихо.</i>")

    total_new = sum(unread.values())
    if total_new:
        lines += ["", f"🆕 Непрочитанных сообщений: <b>{total_new}</b>"]

    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ К каналам", callback_data="chat_menu")
    await safe_edit_text(callback, "\n".join(lines),
                         reply_markup=builder.as_markup(), parse_mode="HTML")


@router.message(ChatForm.waiting_for_search, F.text, F.chat.type == "private")
async def chat_search_run(message: Message, state: FSMContext):
    """Показать результаты поиска."""
    await state.clear()

    async with async_session() as session:
        character = await _character(session, message.from_user.id)
        if character is None:
            await message.answer("Сначала создай героя.")
            return
        results = await C.search(session, message.text, character=character,
                                 limit=15)

    if not results:
        await message.answer(
            "🔎 <i>Ничего не нашлось. Попробуй другое слово.</i>",
            reply_markup=continue_keyboard([("💬 Сообщество", "chat_menu")]),
            parse_mode="HTML")
        return

    lines = [f"🔎 <b>Найдено: {len(results)}</b>", ""]
    for msg, channel in results:
        who = msg.author_name or ("Мир" if msg.is_system else "Кто-то")
        label = channel.label() if channel is not None else "канал"
        lines.append(f"{label} · <b>{who}</b>")
        lines.append(f"   <i>{_shorten(msg.text, 90)}</i>")

    await message.answer("\n".join(lines),
                         reply_markup=continue_keyboard([("💬 Сообщество",
                                                          "chat_menu")]),
                         parse_mode="HTML")


@router.message(ChatForm.waiting_for_text, F.text, F.chat.type == "private")
async def chat_send(message: Message, state: FSMContext):
    """Принять текст и отправить его в канал.

    Ловится ТОЛЬКО в состоянии ввода: обычный текст по-прежнему уходит в
    свой обработчик в start.py, ничего не перехватывается лишнего.
    """
    from bot import community_bridge as bridge

    data = await state.get_data()
    key = data.get("chat_channel", "")
    reply_to = data.get("chat_reply_to")
    await state.clear()

    async with async_session() as session:
        character = await _character(session, message.from_user.id)
    if character is None:
        await message.answer("Сначала создай героя.")
        return

    result = await bridge.relay_from_game(character, key, message.text,
                                          reply_to_id=reply_to)
    if not result.get("ok"):
        await message.answer(f"❌ {result.get('reason', 'Не отправлено.')}")
        return

    tail = ("Сообщение ушло в канал и в группу сообщества."
            if result.get("delivered")
            else "Сообщение записано в канал. Группа сообщества пока не "
                 "подключена — его увидят в боте и в панели.")
    await message.answer(
        f"✅ <b>Отправлено.</b>\n\n<i>{tail}</i>",
        reply_markup=continue_keyboard([("💬 К каналу", f"chat_open:{key}")]),
        parse_mode="HTML")
