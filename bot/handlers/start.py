from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.database import async_session
from core.models import User, Character, Cell, AdminMessage
from bot.keyboards.inline import main_menu_keyboard, class_select_keyboard, confirm_class_keyboard, back_to_main_keyboard
from bot.utils.texts import WELCOME_TEXT, CLASS_DESCRIPTIONS
from core.enums import CharacterClass

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
            reply_markup=main_menu_keyboard(has_character=bool(character)),
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
        if user:
            result = await session.execute(
                select(Character).where(Character.user_id == user.id)
            )
            has_char = result.scalar_one_or_none() is not None

    await callback.message.edit_text(
        WELCOME_TEXT,
        reply_markup=main_menu_keyboard(has_character=has_char),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "create_character")
async def create_character(callback: CallbackQuery):
    await callback.message.edit_text(
        "Выбери класс своего героя:",
        reply_markup=class_select_keyboard(),
    )


@router.callback_query(F.data.startswith("select_class:"))
async def select_class(callback: CallbackQuery):
    cls_value = callback.data.split(":")[1]
    char_class = CharacterClass(cls_value)
    text = CLASS_DESCRIPTIONS.get(char_class, "Неизвестный класс")
    await callback.message.edit_text(
        text,
        reply_markup=confirm_class_keyboard(cls_value),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("confirm_class:"))
async def confirm_class(callback: CallbackQuery):
    cls_value = callback.data.split(":")[1]
    char_class = CharacterClass(cls_value)

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

        stats = {
            CharacterClass.WARRIOR: {"strength": 15, "agility": 8, "intelligence": 5, "endurance": 14, "luck": 8, "max_hp": 140, "max_mp": 30},
            CharacterClass.MAGE: {"strength": 5, "agility": 8, "intelligence": 16, "endurance": 8, "luck": 10, "max_hp": 80, "max_mp": 120},
            CharacterClass.ROGUE: {"strength": 10, "agility": 16, "intelligence": 8, "endurance": 8, "luck": 14, "max_hp": 100, "max_mp": 50},
            CharacterClass.CLERIC: {"strength": 8, "agility": 8, "intelligence": 14, "endurance": 12, "luck": 10, "max_hp": 110, "max_mp": 90},
        }
        s = stats.get(char_class, stats[CharacterClass.WARRIOR])

        result = await session.execute(
            select(Cell).where(Cell.location_id == 1).where(Cell.x == 5).where(Cell.y == 5)
        )
        spawn_cell = result.scalar_one_or_none()

        character = Character(
            user_id=user.id,
            name=callback.from_user.first_name or "Изгнанник",
            character_class=char_class,
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
            cell_id=spawn_cell.id if spawn_cell else None,
        )
        session.add(character)
        await session.commit()

    await callback.message.edit_text(
        f"✅ Герой <b>{character.name}</b> создан!\n\nКласс: <code>{char_class.value}</code>\n\n"
        f"Добро пожаловать в Теневые Земли, изгнанник.",
        reply_markup=main_menu_keyboard(has_character=True),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "help")
async def help_handler(callback: CallbackQuery):
    text = (
        "📜 <b>Помощь</b>\n\n"
        "<b>Основные команды:</b>\n"
        "• Профиль — твои статы, экипировка и золото\n"
        "• Бой — охота на монстров (осмотрись на клетке и ищи 👾)\n"
        "• Инвентарь — управление предметами\n"
        "• Лавка — покупка снаряжения\n"
        "• Подземелье — процедурные данжи (соло)\n\n"
        "<b>Советы:</b>\n"
        "— Мир бесшовный: иди к краю локации, чтобы попасть в соседнюю\n"
        "— Отдыхай, чтобы восстановить здоровье\n"
        "— Продавай лишний хлам торговцу\n"
        "— Пиши админу простым сообщением в бот\n\n"
        "<i>Удачи в Теневых Землях...</i>"
    )
    await callback.message.edit_text(text, reply_markup=back_to_main_keyboard(), parse_mode="HTML")
