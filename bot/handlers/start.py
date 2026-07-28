from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.database import async_session
from core.models import User, Character, Cell, AdminMessage, VisitedCell
from bot.keyboards.inline import main_menu_keyboard, class_select_keyboard, confirm_class_keyboard, back_to_main_keyboard
from bot.utils.texts import WELCOME_TEXT, class_description_text
from bot.utils.photos import send_or_edit_photo
from core.classes import all_classes, get_class

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            user = User(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
            )
            session.add(user)
            await session.commit()

        result = await session.execute(
            select(Character)
            .where(Character.user_id == user.id)
            .options(selectinload(Character.location), selectinload(Character.cell))
        )
        character = result.scalar_one_or_none()

        await message.answer(
            WELCOME_TEXT,
            reply_markup=main_menu_keyboard(
                has_character=bool(character),
                is_admin=bool(user.is_web_admin),
            ),
            parse_mode="HTML",
        )


@router.message(F.text)
async def handle_text(message: Message):
    """Handle text messages from players — check if replying to admin."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            return

        # Save player message
        msg = AdminMessage(user_id=user.id, from_admin=False, text=message.text)
        session.add(msg)
        await session.commit()

        # Notify admin if any unread admin messages exist
        result = await session.execute(
            select(AdminMessage)
            .where(AdminMessage.user_id == user.id)
            .where(AdminMessage.from_admin == True)
            .where(AdminMessage.is_read == False)
        )
        unread = result.scalars().all()
        if unread:
            for m in unread:
                m.is_read = True
            await session.commit()
            await message.answer(
                "📨 <b>Сообщение отправлено администратору.</b>",
                parse_mode="HTML",
            )


@router.callback_query(F.data == "main_menu")
async def main_menu(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        has_char = False
        is_admin = bool(user and user.is_web_admin)
        if user:
            result = await session.execute(
                select(Character).where(Character.user_id == user.id)
            )
            has_char = result.scalar_one_or_none() is not None

    await callback.message.edit_text(
        WELCOME_TEXT,
        reply_markup=main_menu_keyboard(has_character=has_char, is_admin=is_admin),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "create_character")
async def create_character(callback: CallbackQuery):
    """Экран выбора класса. Список берётся из БД, а не из кода —
    новые классы, добавленные в админке, появляются здесь сразу."""
    async with async_session() as session:
        classes = await all_classes(session)

    if not classes:
        await callback.answer(
            "Классы ещё не настроены. Загляни позже.", show_alert=True
        )
        return

    await callback.message.edit_text(
        "Выбери класс своего героя:",
        reply_markup=class_select_keyboard(classes),
    )


@router.callback_query(F.data.startswith("class_page:"))
async def class_page(callback: CallbackQuery):
    page = int(callback.data.split(":")[1])
    async with async_session() as session:
        classes = await all_classes(session)
    await callback.message.edit_text(
        "Выбери класс своего героя:",
        reply_markup=class_select_keyboard(classes, page=page),
    )


@router.callback_query(F.data.startswith("select_class:"))
async def select_class(callback: CallbackQuery):
    cls_key = callback.data.split(":")[1]
    async with async_session() as session:
        cls_def = await get_class(session, cls_key)

    if cls_def is None:
        await callback.answer("Такого класса больше нет.", show_alert=True)
        return

    await send_or_edit_photo(
        callback,
        class_description_text(cls_def),
        reply_markup=confirm_class_keyboard(cls_key),
        image_url=cls_def.image_url,
    )


@router.callback_query(F.data.startswith("confirm_class:"))
async def confirm_class(callback: CallbackQuery):
    cls_key = callback.data.split(":")[1]

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer("Ошибка: пользователь не найден.", show_alert=True)
            return

        result = await session.execute(
            select(Character).where(Character.user_id == user.id)
        )
        if result.scalar_one_or_none():
            await callback.answer("У тебя уже есть персонаж!", show_alert=True)
            return

        cls_def = await get_class(session, cls_key)
        if cls_def is None or not cls_def.is_enabled:
            await callback.answer("Этот класс недоступен.", show_alert=True)
            return

        s = cls_def.base_stats()

        result = await session.execute(
            select(Cell).where(Cell.location_id == 1).where(Cell.x == 5).where(Cell.y == 5)
        )
        spawn_cell = result.scalar_one_or_none()

        character = Character(
            user_id=user.id,
            name=callback.from_user.first_name or "Изгнанник",
            character_class=cls_def.key,
            level=1,
            experience=0,
            gold=50,
            strength=s["strength"],
            agility=s["agility"],
            intelligence=s["intelligence"],
            endurance=s["endurance"],
            luck=s["luck"],
            max_hp=s["max_hp"],
            current_hp=s["max_hp"],
            max_mp=s["max_mp"],
            current_mp=s["max_mp"],
            location_id=1,
            floor=0,
            cell_id=spawn_cell.id if spawn_cell else None,
        )
        session.add(character)
        await session.flush()
        if spawn_cell:
            session.add(VisitedCell(
                character_id=character.id,
                location_id=1,
                floor=0,
                x=spawn_cell.x,
                y=spawn_cell.y,
            ))
        await session.commit()
        char_name = character.name

    await callback.message.edit_text(
        f"✅ Герой <b>{char_name}</b> создан!\n\n"
        f"Класс: {cls_def.icon} <b>{cls_def.name}</b>\n\n"
        f"Добро пожаловать в Теневые Земли, изгнанник.",
        reply_markup=main_menu_keyboard(has_character=True),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "help")
async def help_handler(callback: CallbackQuery):
    text = (
        "📜 <b>Помощь</b>\n\n"
        "<b>Основные команды:</b>\n"
        "• Профиль — статы, экипировка по слотам и золото\n"
        "• Бой — охота на монстров (осмотрись на клетке и ищи 👾)\n"
        "• Инвентарь — надеть, использовать, выбросить\n"
        "• Лавка — покупка снаряжения\n"
        "• Подземелье — процедурные данжи (соло)\n\n"
        "<b>🆔 Уникальные предметы:</b>\n"
        "У каждой вещи свой ID и свои статы — два одинаковых меча всё равно "
        "разные. Смотри «Качество»: чем выше процент, тем удачнее экземпляр.\n\n"
        "<b>🔨 Ремесло:</b>\n"
        "Найди на карте кузнеца, алхимика или ювелира. Он скуёт вещь по рецепту "
        "из твоих материалов и заточит то, что уже носишь. Заточка растит статы, "
        "но при неудаче ресурсы сгорают.\n\n"
        "<b>👾 Монстры:</b>\n"
        "Мобы ходят по карте и восстанавливаются со временем. Слабые могут "
        "забредать в опасные земли, а вот сильные к новичкам не заходят.\n\n"
        "<b>Советы:</b>\n"
        "— Мир бесшовный: иди к краю локации, чтобы попасть в соседнюю\n"
        "— Отдыхай, чтобы восстановить здоровье\n"
        "— Не выбрасывай хлам: лом, шкуры и кости нужны для крафта\n"
        "— Сундуки со временем наполняются заново\n"
        "— Пиши админу простым сообщением в бот\n\n"
        "<i>Удачи в Теневых Землях...</i>"
    )
    await callback.message.edit_text(text, reply_markup=back_to_main_keyboard(), parse_mode="HTML")
