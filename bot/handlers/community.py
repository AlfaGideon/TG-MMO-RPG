"""Чат сообщества внутри бота: список каналов, чтение, отправка.

Экраны для игрока, который не хочет уходить в группу: он видит те же
каналы и те же сообщения, а мост (`bot/community_bridge.py`) доставляет
его реплику в тему супергруппы.

Права нигде здесь не считаются — за них отвечает `core/community.py`.
Гильдейский канал виден участнику гильдии, канал фракции — присягнувшему,
и это одно правило для бота, группы и админки.
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


class ChatForm(StatesGroup):
    """Игрок пишет в канал. Ключ канала лежит в data, а не в имени состояния."""
    waiting_for_text = State()


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


def _channels_keyboard(channels):
    builder = InlineKeyboardBuilder()
    for ch in channels:
        builder.button(text=ch.label(), callback_data=f"chat_open:{ch.key}")
    builder.button(text="◀️ Меню", callback_data="main_menu")
    builder.adjust(1)
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
        info = await C.stats(session)

    lines = ["💬 <b>Сообщество</b>", "",
             "<i>Каналы — как разделы на форуме: у каждого своя тема.</i>", ""]
    for ch in channels:
        mark = ""
        if ch.access == C.ChannelAccess.READONLY.value:
            mark = " <i>(только чтение)</i>"
        elif ch.access == C.ChannelAccess.MEMBERS.value:
            mark = " <i>(закрытый)</i>"
        lines.append(f"{ch.label()}{mark}")
        if ch.topic:
            lines.append(f"   <i>{ch.topic}</i>")
    if not channels:
        lines.append("<i>Пока ни одного канала. Загляни позже.</i>")
    lines += ["", f"<i>Всего сообщений в сообществе: {info['messages']}.</i>"]

    await safe_edit_text(callback, "\n".join(lines),
                         reply_markup=_channels_keyboard(channels),
                         parse_mode="HTML")


@router.callback_query(F.data.startswith("chat_open:"))
async def chat_open(callback: CallbackQuery):
    """Показать последние сообщения канала."""
    key = callback.data.split(":", 1)[1]

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
        messages = await C.recent(session, channel, PAGE_SIZE)
        writable = await C.can_write(session, channel, character)

    lines = [f"{channel.label()}", ""]
    if channel.topic:
        lines += [f"<i>{channel.topic}</i>", ""]
    if not messages:
        lines.append("<i>Здесь ещё тихо. Скажи первое слово.</i>")
    for m in messages:
        if m.is_system:
            lines.append(f"📜 <i>{m.text}</i>")
        else:
            who = m.author_name or "Кто-то"
            lines.append(f"<b>{who}</b>: {m.text}")

    builder = InlineKeyboardBuilder()
    if writable:
        builder.button(text="✍️ Написать", callback_data=f"chat_write:{key}")
    builder.button(text="🔄 Обновить", callback_data=f"chat_open:{key}")
    builder.button(text="◀️ К каналам", callback_data="chat_menu")
    builder.adjust(1)

    await safe_edit_text(callback, "\n".join(lines),
                         reply_markup=builder.as_markup(), parse_mode="HTML")


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
    await state.update_data(chat_channel=key)

    builder = InlineKeyboardBuilder()
    builder.button(text="✖️ Отмена", callback_data=f"chat_cancel:{key}")
    await safe_edit_text(
        callback,
        f"✍️ <b>Сообщение в {label}</b>\n\n"
        f"Напиши текст одним сообщением — оно уйдёт в канал и в группу "
        f"сообщества.\n\n<i>Максимум {C.MESSAGE_LIMIT} символов.</i>",
        reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("chat_cancel:"))
async def chat_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    callback.data = f"chat_open:{callback.data.split(':', 1)[1]}"
    await chat_open(callback)


@router.message(ChatForm.waiting_for_text, F.text, F.chat.type == "private")
async def chat_send(message: Message, state: FSMContext):
    """Принять текст и отправить его в канал.

    Ловится ТОЛЬКО в состоянии ввода: обычный текст по-прежнему уходит в
    свой обработчик в start.py, ничего не перехватывается лишнего.
    """
    from bot import community_bridge as bridge

    data = await state.get_data()
    key = data.get("chat_channel", "")
    await state.clear()

    async with async_session() as session:
        character = await _character(session, message.from_user.id)
    if character is None:
        await message.answer("Сначала создай героя.")
        return

    result = await bridge.relay_from_game(character, key, message.text)
    if not result.get("ok"):
        await message.answer(f"❌ {result.get('reason', 'Не отправлено.')}")
        return

    tail = ("Сообщение ушло в канал и в группу сообщества."
            if result.get("delivered")
            else "Сообщение записано в канал. Группа сообщества пока не "
                 "подключена — его увидят в боте и в панели.")
    await message.answer(f"✅ <b>Отправлено.</b>\n\n<i>{tail}</i>",
                         reply_markup=continue_keyboard(), parse_mode="HTML")
