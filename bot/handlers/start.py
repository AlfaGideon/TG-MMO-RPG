from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from html import escape
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.database import async_session
from core.models import User, Character, Cell, Battle, AdminMessage, VisitedCell, PlayerSuggestion, GameUpdate, Location
from bot.keyboards.inline import (
    main_menu_keyboard, class_select_keyboard, confirm_class_keyboard,
    back_to_main_keyboard, reroll_keyboard, help_menu_keyboard, back_to_help_keyboard,
    faction_select_keyboard,
)
from bot.utils.texts import WELCOME_TEXT, class_description_text, reroll_text
from bot.utils.photos import send_or_edit_photo
from core import magic, statroll
from core.classes import all_classes, get_class
from core.vip import is_vip_active, offline_protected, set_offline
from engine.rules import clean_name
from bot.utils.edit import safe_edit_text

router = Router()


class IdeaForm(StatesGroup):
    """Состояние ввода идеи после нажатия кнопки в разделе помощи."""

    waiting_for_text = State()


def faction_chosen(character) -> bool:
    """Выбрана ли стартовая фракция.

    Вместе с выбором фракции герой получает стартовую репутацию (+50),
    и поле reputation перестаёт быть пустым. До выбора оно '' или None
    (значение по умолчанию в БД) — надёжный маркер незавершённого шага.
    """
    return bool((getattr(character, "reputation", "") or "").strip())


RESUME_HINT = (
    "⚠️ <b>Создание героя прервалось.</b>\n"
    "Продолжим с того самого места, где ты остановился!\n\n"
)


async def resume_character_creation(event, session, character) -> bool:
    """Возвращает героя на прерванный шаг создания вместо главного меню.

    Раньше /start (и кнопка «Меню») всегда открывали главное меню. Если
    сервер обновлялся, пока игрок катал статы или не успел выбрать
    фракцию, герой оказывался «в игре» без локации — меню показывало
    полный набор кнопок, а «Карта мира» и другие разделы падали на
    character.location = None. Теперь старт возвращает на последний
    шаг создания: экран переката статов или выбор фракции.

    event может быть Message (команда /start) или CallbackQuery
    (кнопка «Меню»). Возвращает True, если вместо меню показан экран
    продолжения создания.
    """
    if character.stats_locked and faction_chosen(character):
        return False

    cls_def = None
    if not character.stats_locked:
        cls_def = await get_class(session, character.character_class)

    if not character.stats_locked and cls_def is not None:
        # Игрок остановился на броске статов — показываем экран переката
        # с текущим броском и остатком попыток.
        base = cls_def.base_stats()
        rolled = {k: getattr(character, k) for k in statroll.ROLLED_STATS}
        affinities = await magic.get_affinities(session, character.id)
        text = RESUME_HINT + reroll_text(character, cls_def, base, rolled, affinities)
        markup = reroll_keyboard(character.id, character.rerolls_left)
        if isinstance(event, CallbackQuery):
            await send_or_edit_photo(
                event, text, reply_markup=markup, image_url=cls_def.image_url,
            )
            await event.answer()
        else:
            await send_or_edit_photo(
                event, text, reply_markup=markup, image_url=cls_def.image_url,
            )
        return True

    # Статы зафиксированы, но фракция не выбрана (либо класс удалили —
    # тогда тоже отправляем выбирать фракцию, чтобы не застрять).
    await _show_faction_page(event, character.id, prefix=RESUME_HINT)
    return True


def _class_book_text(cls_def, page: int, total: int) -> str:
    """Текст страницы «книги классов» на старте."""
    return (
        f"📖 <b>Книга классов</b> — страница <b>{page + 1}</b> из <b>{total}</b>\n\n"
        f"{class_description_text(cls_def)}\n\n"
        "<i>Листай страницы, сравнивай бонусы и нажми «Выбрать и далее», "
        "когда определишься.</i>"
    )


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

        # Герой есть, но создание не завершено (перекат статов или выбор
        # фракции прервались, например обновлением сервера) — возвращаем
        # на последний шаг, а не в меню.
        if character and await resume_character_creation(message, session, character):
            return

        await message.answer(
            WELCOME_TEXT,
            reply_markup=main_menu_keyboard(
                has_character=bool(character),
                is_admin=bool(user.is_web_admin),
                is_vip=bool(character and is_vip_active(character)),
                offline=bool(character and offline_protected(character)),
            ),
            parse_mode="HTML",
        )


@router.message(F.text)
async def handle_text(message: Message, state: FSMContext):
    """Обрабатывает ответы игрока, включая идею из раздела помощи.

    Раньше кнопка «Предложить идею» только показывала инструкцию, поэтому
    игроку нужно было самому угадать, что сообщение надо начинать со слова
    «Идея». Теперь кнопка действительно переводит бота в режим ввода: любое
    следующее текстовое сообщение сохраняется как идея.
    """
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            return

        text_lower = message.text.lower().strip()
        idea_mode = await state.get_state() == IdeaForm.waiting_for_text.state
        explicit_idea = text_lower.startswith("идея") or text_lower.startswith("idea")
        if idea_mode or explicit_idea:
            # В режиме кнопки принимаем обычный текст. Старый формат
            # «Идея: ...» тоже оставляем рабочим для совместимости.
            idea_content = message.text.strip()
            if explicit_idea:
                for prefix in ("идея:", "идея", "idea:", "idea"):
                    if text_lower.startswith(prefix):
                        idea_content = message.text[len(prefix):].strip()
                        break

            if not idea_content:
                await message.answer(
                    "💡 Напиши текст идеи одним сообщением — например: «Добавить почтовый ящик между игроками»."
                )
                return

            result = await session.execute(
                select(Character).where(Character.user_id == user.id)
            )
            character = result.scalar_one_or_none()
            if not character:
                await state.clear()
                await message.answer("Сначала создай персонажа, чтобы предлагать идеи!")
                return

            # Не даём случайному огромному сообщению переполнить админскую
            # карточку и Telegram-уведомление.
            idea_content = idea_content[:4000]
            suggestion = PlayerSuggestion(
                character_id=character.id,
                text=idea_content,
                status="pending"
            )
            session.add(suggestion)
            await session.commit()
            await state.clear()

            await message.answer(
                "💡 <b>Идея отправлена разработчикам!</b>\n\n"
                "Она появилась в админ-панели в разделе «Обновления и Идеи» и будет рассмотрена. "
                "Когда статус изменится, бот пришлёт тебе уведомление.\n\n"
                "Спасибо за помощь в развитии игры! 🤝",
                parse_mode="HTML"
            )
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


@router.callback_query(F.data == "bot_suggest")
async def bot_suggest_handler(callback: CallbackQuery, state: FSMContext):
    await state.set_state(IdeaForm.waiting_for_text)
    text = (
        "💡 <b>Место для идей игроков</b>\n\n"
        "Напиши одним следующим сообщением любую идею, пожелание или замечание по игре. "
        "Я передам её разработчикам в админ-панель — добавлять слово «Идея» больше не нужно.\n\n"
        "<b>Пример:</b>\n"
        "<code>Добавить больше редкого оружия во 2-ю локацию</code>\n\n"
        "<i>Можно отменить отправку кнопкой «Назад».</i>"
    )
    await safe_edit_text(callback, text, reply_markup=back_to_help_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "offline_toggle")
async def offline_toggle(callback: CallbackQuery):
    """VIP leaves the world: no combat, mobs, PvP or world effects can touch them."""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = result.scalar_one_or_none()
        character = None
        if user:
            result = await session.execute(select(Character).where(Character.user_id == user.id))
            character = result.scalar_one_or_none()
        if not character or not is_vip_active(character):
            await callback.answer("Режим «Я офлайн» доступен только VIP.", show_alert=True)
            return
        active_battle = (await session.execute(
            select(Battle).where(Battle.character_id == character.id)
            .where(Battle.result.is_(None))
        )).scalar_one_or_none()
        if active_battle:
            await callback.answer("Сначала закончи бой.", show_alert=True)
            return
        set_offline(character, True)
        await session.commit()
    await safe_edit_text(callback, "🌙 <b>Ты офлайн</b>\n\n"
        "👑 VIP-защита включена: мобы, игроки, бои и катаклизмы тебя не затрагивают.\n\n"
        "Все действия скрыты до возвращения в мир.",
        reply_markup=main_menu_keyboard(has_character=True, is_vip=True, offline=True),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "offline_resume")
async def offline_resume(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = result.scalar_one_or_none()
        character = None
        if user:
            result = await session.execute(
                select(Character).where(Character.user_id == user.id)
                .options(selectinload(Character.location), selectinload(Character.cell))
            )
            character = result.scalar_one_or_none()
        if not character or not character.cell:
            await callback.answer("Персонаж не найден.", show_alert=True)
            return
        character.offline_protected = False
        await session.commit()
        await callback.answer("Ты снова в мире.")
        # Единственная доступная кнопка действительно возвращает в текущую
        # клетку мира, а не просто открывает ещё одно меню.
        from bot.handlers.location import show_cell
        await show_cell(callback, character, character.location, session)


@router.callback_query(F.data == "main_menu")
async def main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        character = None
        has_char = False
        is_admin = bool(user and user.is_web_admin)
        if user:
            result = await session.execute(
                select(Character).where(Character.user_id == user.id)
            )
            character = result.scalar_one_or_none()
            has_char = character is not None

        # Как и /start: если создание героя не завершено, «Меню» ведёт
        # не в меню, а на прерванный шаг создания.
        if character and await resume_character_creation(callback, session, character):
            return

    await safe_edit_text(
        callback,
        WELCOME_TEXT,
        reply_markup=main_menu_keyboard(
            has_character=has_char, is_admin=is_admin,
            is_vip=bool(character and is_vip_active(character)),
            offline=bool(character and offline_protected(character)),
        ),
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

    page = 0
    cls_def = classes[page]
    await send_or_edit_photo(
        callback,
        _class_book_text(cls_def, page, len(classes)),
        reply_markup=class_select_keyboard(classes, page=page),
        image_url=cls_def.image_url,
    )


@router.callback_query(F.data.startswith("class_page:"))
async def class_page(callback: CallbackQuery):
    page = int(callback.data.split(":")[1])
    async with async_session() as session:
        classes = await all_classes(session)

    if not classes:
        await callback.answer("Классы ещё не настроены.", show_alert=True)
        return

    page = max(0, min(page, len(classes) - 1))
    cls_def = classes[page]
    await send_or_edit_photo(
        callback,
        _class_book_text(cls_def, page, len(classes)),
        reply_markup=class_select_keyboard(classes, page=page),
        image_url=cls_def.image_url,
    )


@router.callback_query(F.data.startswith("select_class:"))
async def select_class(callback: CallbackQuery):
    cls_key = callback.data.split(":")[1]
    async with async_session() as session:
        cls_def = await get_class(session, cls_key)
        classes = await all_classes(session)

    if cls_def is None:
        await callback.answer("Такого класса больше нет.", show_alert=True)
        return

    back_page = next((i for i, item in enumerate(classes) if item.key == cls_key), None)
    await send_or_edit_photo(
        callback,
        class_description_text(cls_def),
        reply_markup=confirm_class_keyboard(cls_key, back_page=back_page),
        image_url=cls_def.image_url,
    )


@router.callback_query(F.data.startswith("confirm_class:"))
async def confirm_class(callback: CallbackQuery):
    """Создаёт героя со случайными статами и бросает дар к магии.

    Статы катаются от базы класса в диапазоне −10 %…+20 %, и игроку сразу
    даётся 10 попыток переката — принять можно любой бросок.
    """
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

        base = cls_def.base_stats()
        rolled = statroll.roll_stats(base)

        character = Character(
            user_id=user.id,
            # first_name может содержать <>& и сломать HTML-разметку всех
            # сообщений бота, куда попадает имя, — чистим на входе.
            name=clean_name(callback.from_user.first_name, "Изгнанник"),
            character_class=cls_def.key,
            level=1,
            experience=0,
            gold=50,
            # Класс и стартовые статы ещё не помещают героя в мир.
            # Локация и клетка определятся только после принятия статов и
            # осознанного выбора фракции.
            location_id=None,
            cell_id=None,
            floor=0,
            rerolls_left=statroll.DEFAULT_REROLLS,
            stats_locked=False,
            **rolled,
        )
        character.current_hp = character.max_hp
        character.current_mp = character.max_mp
        session.add(character)
        await session.flush()

        # Дар к магии бросается один раз и перекатом не меняется —
        # с чем родился, с тем и живёшь.
        pairs = magic.roll_affinities(cls_def)
        await magic.set_affinities(session, character, pairs)
        affinities = await magic.get_affinities(session, character.id)

        await session.commit()
        char_id = character.id

    await send_or_edit_photo(
        callback,
        reroll_text(character, cls_def, base, rolled, affinities),
        reply_markup=reroll_keyboard(char_id, character.rerolls_left),
        image_url=cls_def.image_url,
    )


@router.callback_query(F.data.startswith("reroll_stats:"))
async def reroll_stats(callback: CallbackQuery):
    """Перекатывает стартовые статы, пока есть попытки."""
    char_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        character = await session.get(Character, char_id)
        if character is None:
            await callback.answer("Персонаж не найден.", show_alert=True)
            return

        # Чужой персонаж перекатывать нельзя
        user = await session.get(User, character.user_id)
        if user is None or user.telegram_id != callback.from_user.id:
            await callback.answer("Это не твой герой.", show_alert=True)
            return

        if character.stats_locked:
            await callback.answer("Статы уже зафиксированы.", show_alert=True)
            return
        if (character.rerolls_left or 0) <= 0:
            await callback.answer("Попытки закончились.", show_alert=True)
            return

        cls_def = await get_class(session, character.character_class)
        base = cls_def.base_stats() if cls_def else {}
        rolled = statroll.roll_stats(base)
        statroll.apply_stats(character, rolled)
        character.rerolls_left = (character.rerolls_left or 0) - 1

        # Попытки кончились — бросок становится окончательным
        if character.rerolls_left <= 0:
            character.stats_locked = True

        affinities = await magic.get_affinities(session, character.id)
        await session.commit()
        locked = character.stats_locked
        left = character.rerolls_left

    if locked:
        await _show_faction_page(callback, char_id)
        return

    await safe_edit_text(
        callback,
        reroll_text(character, cls_def, base, rolled, affinities),
        reply_markup=reroll_keyboard(char_id, left),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("accept_stats:"))
async def accept_stats(callback: CallbackQuery):
    """Фиксирует текущий бросок и завершает создание героя."""
    char_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        character = await session.get(Character, char_id)
        if character is None:
            await callback.answer("Персонаж не найден.", show_alert=True)
            return

        user = await session.get(User, character.user_id)
        if user is None or user.telegram_id != callback.from_user.id:
            await callback.answer("Это не твой герой.", show_alert=True)
            return

        character.stats_locked = True
        character.rerolls_left = 0
        character.current_hp = character.max_hp
        character.current_mp = character.max_mp
        cls_def = await get_class(session, character.character_class)
        affinities = await magic.get_affinities(session, character.id)
        await session.commit()
        base = cls_def.base_stats() if cls_def else {}
        rolled = {k: getattr(character, k) for k in statroll.ROLLED_STATS}

    await _show_faction_page(callback, char_id)


# ── Книга выбора фракции ────────────────────────────────────
#
# Выбор фракции устроен как книга классов: игрок листает страницы,
# на каждой — герб (картинка 1:1), описание и все стартовые бонусы.
# Одной простынёй текста и слепых кнопок больше нет.

# Гербы лежат в admin/static/factions — бот читает их прямо с диска
# (get_photo_input превращает /static/... в admin/static/...).
FACTION_IMAGES = {
    "guard": "/static/factions/guard.jpg",
    "scavengers": "/static/factions/scavengers.jpg",
    "cult": "/static/factions/cult.jpg",
    "order": "/static/factions/order.jpg",
}

# Союз по диагонали кольца: противоположные стороны не враждуют.
_FACTION_ALLY = {
    "guard": "cult",
    "scavengers": "order",
    "cult": "guard",
    "order": "scavengers",
}

FACTION_CARDS = {
    "guard": {
        "castle": "Замок Пепла",
        "side": "юго-восток",
        "desc": (
            "Старейший порядок Теневых Земель. Воины Погоста клялись: "
            "ни одна нежить не переступит порог, пока жив хоть один "
            "стражник. Стены их крепости не раз выдерживали волны "
            "нежити и катаклизмы — и не раз падали, чтобы встать снова."
        ),
        "bonus": "+3 Выносливость ❤️",
        "reward": "100🟤",
    },
    "scavengers": {
        "castle": "Замок Глубин",
        "side": "юго-запад",
        "desc": (
            "Гильдия выросла из бродячих скупщиков и могильщиков, "
            "понявших: на войне и бедствиях можно неплохо жить. "
            "Торгует дешевле всех, платит за мародёрство, ценит "
            "добытчиков — а подземные ходы её замка ведут к "
            "сокровищам, которые другие боятся взять."
        ),
        "bonus": "+2 Удача 🍀, +1 Ловкость 🏃",
        "reward": "200🟤",
    },
    "cult": {
        "castle": "Замок Теней",
        "side": "северо-восток",
        "desc": (
            "Культ знает: мир обречён, и Раскол — лишь первое дыхание "
            "конца. Его послушники приближают катаклизмы и щедро "
            "платят тем, кто помогает им случиться, — ведь после конца "
            "начнётся нечто новое. В вечных сумерках замка звучат "
            "пророчества."
        ),
        "bonus": "+3 Интеллект 🧠",
        "reward": "100🟤 + Осколок души",
    },
    "order": {
        "castle": "Замок Рассвета",
        "side": "северо-запад",
        "desc": (
            "Рыцари-паломники, несущие свет в Теневые Земли. Их вера "
            "проста: тьма конечна, а свет — нет. Их замок — единственное "
            "место, где солнце светит дольше обычного; Орден хранит "
            "реликвии, сжигает нежить и сдерживает старые клятвы."
        ),
        "bonus": "+2 Сила 💪, +1 Выносливость 🛡",
        "reward": "100🟤",
    },
}


def _faction_page_text(page: int, prefix: str = "") -> str:
    """Страница книги выбора: герб + описание + все бонусы фракции.

    Влезает в лимит подписи к фото (1024 символа) — проверяется
    тестом, поэтому описания держим ёмкими.
    """
    from engine.factions import FACTIONS, ORDER

    page = max(0, min(page, len(ORDER) - 1))
    key = ORDER[page]
    icon, name, motto, foe = FACTIONS[key]
    card = FACTION_CARDS[key]
    ally = _FACTION_ALLY.get(key)

    lines = [
        f"🌍 <b>Выбери свою фракцию</b> — страница <b>{page + 1}</b> из <b>{len(ORDER)}</b>",
        "",
        f"{icon} <b>{name}</b>",
        f"<i>«{motto}»</i>",
        "",
        card["desc"],
        "",
        f"🏰 Стартовый замок: <b>{card['castle']}</b> ({card['side']})",
        f"✨ Бонус характеристик: <b>{card['bonus']}</b>",
        f"🧭 Стартовая репутация: <b>+50</b> (звание «Знакомый»)",
        f"🎁 Награда: <b>{card['reward']}</b>",
    ]
    if foe in FACTIONS:
        lines.append(f"⚔️ Соперник: {FACTIONS[foe][0]} {FACTIONS[foe][1]}")
    if ally in FACTIONS:
        lines.append(f"🤝 Союзник: {FACTIONS[ally][0]} {FACTIONS[ally][1]}")
    lines += [
        "",
        "<i>Листай страницы и сравнивай. Истории сил — в «Книге лора».</i>",
    ]
    return prefix + "\n".join(lines)


async def _show_faction_page(event, char_id: int, page: int = 0, prefix: str = ""):
    """Показать страницу книги выбора фракции с её гербом."""
    from engine.factions import ORDER

    page = max(0, min(page, len(ORDER) - 1))
    await send_or_edit_photo(
        event,
        _faction_page_text(page, prefix=prefix),
        reply_markup=faction_select_keyboard(char_id, page),
        image_url=FACTION_IMAGES.get(ORDER[page]),
    )
    if isinstance(event, CallbackQuery):
        await event.answer()

# ── Книга лора фракций ──────────────────────────────────────

FACTION_LORE_CIRCLE = (
    "📖 <b>Книга фракций</b>\n\n"
    "Четыре силы делят Теневые Земли — и ни одну из них нельзя назвать "
    "доброй или злой. Каждая следует своему пониманию того, как выжить "
    "в мире после Раскола.\n\n"
    "Их отношения замкнуты в <b>кольцо вражды</b>: каждая сила ненавидит "
    "следующую и ненавидима предыдущей. Помощь одной фракции неминуемо "
    "злит её соперника — быть своим для всех невозможно.\n\n"
    "🔁 <b>Кольцо вражды:</b>\n\n"
    "   🛡 Стража  →  ненавидит  💰 Гильдию\n"
    "   💰 Гильдия  →  ненавидит  🌑 Культ\n"
    "   🌑 Культ   →  ненавидит  ⚜️ Орден\n"
    "   ⚜️ Орден   →  ненавидит  🛡 Стражу\n\n"
    "Кольцо замкнуто: каждый враг чьего-то врага — и каждый "
    "союзник чьего-то союзника.\n\n"
    "🤝 <b>Союзы:</b> противоположные стороны кольца не враждуют:\n"
    "   • 🛡 Стража + 🌑 Культ — порядок и хаос, объединённые "
    "общим врагом\n"
    "   • 💰 Гильдия + ⚜️ Орден — нажива и честь, связанные "
    "противоположным врагом\n\n"
    "<b>Схема:</b>\n"
    "<code>   🛡 Стража ← ⚜️ Орден\n"
    "     ↓              ↑\n"
    "   💰 Гильдия → 🌑 Культ</code>\n\n"
    "<i>Листай дальше, чтобы узнать историю каждой фракции.</i>"
)

FACTION_LORE = {
    "guard": (
        "🛡 <b>Стража Погоста</b>\n\n"
        "<b>Девиз:</b> <i>«Пока стоит частокол — стоит и деревня.»</i>\n\n"
        "Стража — старейший порядок Теневых Земель. Ещё до Раскола воины "
        "Погоста обнесли первый лагерь частоколом из костей павших и дали "
        "клятву: ни одна нежить не переступит порог, пока жив хоть один "
        "стражник.\n\n"
        "С годами лагерь вырос в Замок Пепла — крепость на юго-востоке, "
        "чьи стены не раз выдерживали волны нежити и катаклизмы. Стража "
        "платит за убитую нежить и отдаляет бедствия — каждый мёртвый "
        "скелет на их совести.\n\n"
        "⚔️ <b>Враг в кольце:</b> Гильдия падальщиков. Стража ненавидит "
        "мародёров, которые грабят могилы и оскверняют павших — то, ради "
        "чего стражники положили жизни, для падальщиков — лишь нажива.\n\n"
        "🤝 <b>Союзник:</b> Культ Пожирателя. Парадокс? Стража и Культ "
        "по разные стороны баррикад — но в кольце вражды у них общий "
        "враг: Гильдия. Враг моего врага — не друг, но и не соперник.\n\n"
        "⚔️ <b>Кто ненавидит Стражу:</b> Орден Рассвета. Рыцари света "
        "видят в стражниках тех, кто закрывается стенами, пока мир "
        "сгорает. Порядок без света — лишь тень порядка."
    ),
    "scavengers": (
        "💰 <b>Гильдия падальщиков</b>\n\n"
        "<b>Девиз:</b> <i>«Мёртвым золото ни к чему.»</i>\n\n"
        "Когда Раскол обрушил старый мир, первыми, кто научился на нём "
        "зарабатывать, были не воины и не жрецы — а те, кто подбирал "
        "оставшееся. Гильдия выросла из бродячих скупщиков и могильщиков, "
        "что поняли: на войне и бедствиях можно неплохо жить.\n\n"
        "Их оплот — Замок Глубин на юго-западе, где подземные ходы "
        "ведут к сокровищам, которые другие боятся взять. Гильдия "
        "торгует дешевле, платит за мародёрство и ценит добытчиков.\n\n"
        "⚔️ <b>Враг в кольце:</b> Культ Пожирателя. Культисты ускоряют "
        "катаклизмы, а Гильдия теряет на хаосе: рушатся торговые пути, "
        "гибнут покупатели, исчезают товары. Бизнес любит порядок.\n\n"
        "🤝 <b>Союзник:</b> Орден Рассвета. Гильдия и Орден не враждуют — "
        "их интересы совпадают: обе силы ненавидят Культ. Падальщики "
        "снабжают рыцарей, а те — защищают караваны.\n\n"
        "⚔️ <b>Кто ненавидит Гильдию:</b> Стража Погоста. Мародёрство "
        "оскорбляет стражников — но как только Стража и Гильдия "
        "объединяются против Культа, вражда меркнет."
    ),
    "cult": (
        "🌑 <b>Культ Пожирателя</b>\n\n"
        "<b>Девиз:</b> <i>«Всё кончится. Мы лишь торопим неизбежное.»</i>\n\n"
        "Пожиратель — древняя сущность, чьё имя произносят шёпотом. "
        "Культ утверждает, что мир уже обречён, и Раскол — лишь первое "
        "дыхание конца. Культисты не сумасшедшие: они видят, как "
        "катаклизмы становятся всё чаще, как нежить крепнет, "
        "как свет меркнет — и принимают это как истину.\n\n"
        "Их обитель — Замок Теней на северо-востоке, где "
        "вечные сумерки скрывают ритуалы и пророчества. "
        "Культ приближает катаклизмы и щедро платит тем, кто помогает "
        "им случиться — ведь после конца начнётся нечто новое.\n\n"
        "⚔️ <b>Враг в кольце:</b> Орден Рассвета. Священная война. "
        "Культ торопит конец света, Орден — не даёт ему наступить. "
        "Тьма и свет — две стороны одной медали, и между ними "
        "нет мира.\n\n"
        "🤝 <b>Союзник:</b> Стража Погоста. Культ и Стража не враждуют "
        "напрямую — в кольце их разделяет Гильдия. Стража защищает "
        "земли от нежити, Культ управляет хаосом — и порой их "
        "интересы странным образом совпадают.\n\n"
        "⚔️ <b>Кто ненавидит Культ:</b> Гильдия падальщиков. Хаос "
        "разрушает бизнес — и скупщики не прощают убытков."
    ),
    "order": (
        "⚜️ <b>Орден Рассвета</b>\n\n"
        "<b>Девиз:</b> <i>«Свет не просит разрешения — он просто приходит.»</i>\n\n"
        "Орден Рассвета — рыцари-паломники, несущие свет в Теневые Земли. "
        "Когда Раскол погрузил мир во тьму, они не испугались — "
        "зажгли факелы и пошли навстречу. Их вера проста: тьма конечна, "
        "а свет — нет. Каждая убитая нежить — это ещё один луч рассвета.\n\n"
        "Их твердыня — Замок Рассвета на северо-западе, единственное "
        "место, где солнце светит дольше обычного. Орден хранит реликвии, "
        "сжигает нежить и сдерживает старые клятвы, которые иначе "
        "канули бы в бездну.\n\n"
        "⚔️ <b>Враг в кольце:</b> Стража Погоста. Рыцари света презирают "
        "тех, кто прячется за стенами, пока мир сгорает. Порядок без "
        "света — лишь клетка. Стражники видят в Ордене фанатиков, "
        "которые сжигают деревни ради «очищения».\n\n"
        "🤝 <b>Союзник:</b> Гильдия падальщиков. Орден и Гильдия "
        "не враждуют — их объединяет общий враг Культ. Падальщики "
        "снабжают рыцарей, а Орден — открывает путь к сокровищам "
        "в самых тёмных углах мира.\n\n"
        "⚔️ <b>Кто ненавидит Орден:</b> Культ Пожирателя. Свет — "
        "единственное, что Культ не может поглотить. Рыцари "
        "Рассвета — единственная сила, которая заставляет "
        "культистов отступать."
    ),
}


_CAPTION_LIMIT = 1024  # лимит подписи к фото в Telegram


def _split_caption(text: str, budget: int) -> list:
    """Разрезать длинный текст на куски по абзацам, каждый ≤ budget.

    Подпись к фото в Telegram — максимум 1024 символа. Лор-страница
    длиннее, и Telegram отклонял отправку — глава приходила вообще без
    герба (тихий фолбэк в чистый текст). Режем по абзацам, чтобы каждая
    страница книги лора с гербом гарантированно проходила.
    """
    chunks, current = [], ""
    for para in text.split("\n\n"):
        candidate = para if not current else current + "\n\n" + para
        if len(candidate) <= budget:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = para
        # Абзац сам длиннее бюджета — режем по строкам.
        while len(current) > budget:
            cut = current.rfind("\n", 0, budget)
            if cut < budget // 2:
                cut = budget
            chunks.append(current[:cut])
            current = current[cut:].lstrip("\n")
    if current:
        chunks.append(current)
    return chunks or [""]


def _faction_lore_pages() -> list:
    """Страницы книги лора: вступление + главы фракций.

    Возвращает список {'key': код фракции или None, 'text': подпись}.
    Страницам с ключом при показе достаётся герб фракции; глава режется
    на части так, чтобы подпись влезала в лимит вместе с гербом.
    """
    from engine.factions import FACTIONS, ORDER, RIVALS

    pages = [{"key": None, "text": FACTION_LORE_CIRCLE}]
    for key in ORDER:
        icon, name = FACTIONS[key][0], FACTIONS[key][1]
        parts = _split_caption(FACTION_LORE[key], budget=780)
        for idx, part in enumerate(parts):
            if len(parts) > 1:
                part += f"\n\n<i>— {icon} {name}: часть {idx + 1} из {len(parts)} —</i>"
            if idx == len(parts) - 1:
                rival_name = FACTIONS[RIVALS[key]][1]
                ally_name = FACTIONS[_FACTION_ALLY[key]][1]
                part += (
                    f"\n\n⚔️ <b>Соперник:</b> {rival_name}\n"
                    f"🤝 <b>Союзник:</b> {ally_name}\n\n"
                    f"<i>Листай страницы, чтобы узнать о каждой силе, "
                    f"или вернись к выбору фракции.</i>"
                )
            pages.append({"key": key, "text": part})
    return pages


def _faction_lore_text(page: int = 0):
    """Текст страницы книги лора фракций + ключ фракции для герба."""
    pages = _faction_lore_pages()
    page = max(0, min(page, len(pages) - 1))
    entry = pages[page]
    if page == 0:
        # У вступления свой заголовок и схема кольца вражды.
        return entry["key"], entry["text"]
    header = (
        f"📖 <b>Книга фракций</b> — страница <b>{page + 1}</b> из <b>{len(pages)}</b>\n\n"
    )
    return entry["key"], header + entry["text"]


@router.callback_query(F.data.startswith("faction_page:"))
async def faction_page_callback(callback: CallbackQuery):
    """Листание книги выбора фракции: соседние гербы и бонусы."""
    parts = callback.data.split(":")
    char_id = int(parts[1])
    page = int(parts[2])
    await _show_faction_page(callback, char_id, page)


async def _show_faction_lore_page(callback: CallbackQuery, char_id: int,
                                  sel_page: int, page: int):
    """Страница книги лора фракций; на главах сил висит их герб.

    Подписи к фото ограничены 1024 символами — страницы лора бьются на
    части (см. _faction_lore_pages), иначе Telegram отклоняет send и
    глава приходит без картинки.
    """
    pages = _faction_lore_pages()
    total = len(pages)
    page = max(0, min(page, total - 1))
    key, text = _faction_lore_text(page)

    builder = InlineKeyboardBuilder()
    rows = []
    nav = 0
    if page > 0:
        builder.button(text="⬅️ Пред. страница",
                       callback_data=f"faction_lore_page:{char_id}:{sel_page}:{page - 1}")
        nav += 1
    if page + 1 < total:
        builder.button(text="След. страница ➡️",
                       callback_data=f"faction_lore_page:{char_id}:{sel_page}:{page + 1}")
        nav += 1
    if nav:
        rows.append(nav)
    builder.button(text="◀️ Назад к выбору",
                   callback_data=f"faction_lore_back:{char_id}:{sel_page}")
    rows.append(1)
    builder.adjust(*rows)

    image_url = FACTION_IMAGES.get(key) if key else None
    await send_or_edit_photo(
        callback, text, reply_markup=builder.as_markup(), image_url=image_url
    )


@router.callback_query(F.data.startswith("faction_lore:"))
async def faction_lore_callback(callback: CallbackQuery):
    """Книга лора фракций: вступление со схемой круговой вражды.

    Открывается из книги выбора фракции — запоминаем, с какой страницы
    выбора игрок сюда пришёл, чтобы вернуть его туда же.
    """
    parts = callback.data.split(":")
    char_id = int(parts[1])
    sel_page = int(parts[2]) if len(parts) > 2 else 0
    await _show_faction_lore_page(callback, char_id, sel_page, 0)


@router.callback_query(F.data.startswith("faction_lore_page:"))
async def faction_lore_page_callback(callback: CallbackQuery):
    """Листание книги лора фракций."""
    parts = callback.data.split(":")
    char_id = int(parts[1])
    sel_page = int(parts[2]) if len(parts) > 3 else 0
    page = int(parts[3]) if len(parts) > 3 else int(parts[2])
    await _show_faction_lore_page(callback, char_id, sel_page, page)


@router.callback_query(F.data.startswith("faction_lore_back:"))
async def faction_lore_back_callback(callback: CallbackQuery):
    """Возврат из книги лора на ту же страницу книги выбора фракции."""
    parts = callback.data.split(":")
    char_id = int(parts[1])
    sel_page = int(parts[2]) if len(parts) > 2 else 0
    await _show_faction_page(callback, char_id, sel_page)


@router.callback_query(F.data.startswith("start_faction:"))
async def start_faction_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    char_id = int(parts[1])
    faction_key = parts[2]

    if faction_key not in FACTION_CARDS:
        await callback.answer("Такой фракции нет.", show_alert=True)
        return
    loc_name = FACTION_CARDS[faction_key]["castle"]

    async with async_session() as session:
        character = await session.get(Character, char_id)
        if character is None:
            await callback.answer("Персонаж не найден.", show_alert=True)
            return

        owner = await session.get(User, character.user_id)
        if owner is None or owner.telegram_id != callback.from_user.id:
            await callback.answer("Это не твой герой.", show_alert=True)
            return
        if not character.stats_locked:
            await callback.answer("Сначала прими стартовые статы.", show_alert=True)
            return
        if faction_chosen(character):
            await callback.answer("Фракция уже выбрана.", show_alert=True)
            return

        loc_res = await session.execute(
            select(Location).where(Location.name == loc_name)
        )
        loc = loc_res.scalar_one_or_none()
        if not loc:
            loc_res = await session.execute(
                select(Location).where(Location.id == 1)
            )
            loc = loc_res.scalar_one()

        # Спавн — в правильном внутреннем замке 10×10 угловой локации
        # (внешний угол: (0,0)->(5,5), (9,0)->(5,19), (0,9)->(19,5), (9,9)->(19,19)),
        # а не в центре-площади.
        from core.seed import castle_spawn_cell
        spawn_cell = await castle_spawn_cell(session, loc)
        if spawn_cell is None:
            cell_res = await session.execute(
                select(Cell)
                .where(Cell.location_id == loc.id)
                .where(Cell.floor == 0)
                .where(Cell.is_passable == True)
            )
            cells = cell_res.scalars().all()
            center = loc.grid_size // 2
            spawn_cell = (min(cells, key=lambda c: (c.x - center) ** 2 + (c.y - center) ** 2)
                          if cells else None)

        character.location_id = loc.id
        character.cell_id = spawn_cell.id if spawn_cell else None
        character.floor = 0

        # Apply starting bonuses
        from engine.currency import add_currency
        if faction_key == "guard":
            character.endurance += 3
            add_currency(character, bronze=100)
            bonus_desc = "+3 Выносливость ❤️, 100🟤"
        elif faction_key == "scavengers":
            character.luck += 2
            character.agility += 1
            add_currency(character, bronze=200)
            bonus_desc = "+2 Удача 🍀, +1 Ловкость 🏃, 200🟤"
        elif faction_key == "cult":
            character.intelligence += 3
            add_currency(character, bronze=100)
            from core.models import Item, InventoryItem
            soul_item_res = await session.execute(
                select(Item).where(Item.name == "Осколок души")
            )
            soul_item = soul_item_res.scalar_one_or_none()
            if soul_item:
                session.add(InventoryItem(
                    character_id=character.id,
                    item_id=soul_item.id,
                    quantity=1
                ))
            bonus_desc = "+3 Интеллект 🧠, 100🟤, Осколок души 💎"
        elif faction_key == "order":
            character.strength += 2
            character.endurance += 1
            add_currency(character, bronze=100)
            bonus_desc = "+2 Сила 💪, +1 Выносливость 🛡, 100🟤"

        # Initial reputation
        import core.factions as core_factions
        reputation = {faction_key: 50}
        core_factions.save(character, reputation)

        if spawn_cell:
            session.add(VisitedCell(
                character_id=character.id,
                location_id=loc.id,
                floor=0,
                x=spawn_cell.x,
                y=spawn_cell.y,
            ))

        await session.commit()
        loc_name_full = loc.name
        joined_payload = {
            "character_id": character.id,
            "name": character.name,
            "telegram_id": callback.from_user.id,
            "class": character.character_class,
            "level": character.level,
            "location_id": character.location_id,
        }

    # Для живой карты герой появляется только сейчас: класс и статы уже
    # приняты, фракция выбрана, реальная стартовая клетка назначена.
    try:
        from core.realtime import publish as rt_publish
        await rt_publish("player_joined", joined_payload)
    except Exception:
        pass

    await send_or_edit_photo(
        callback,
        f"🎉 <b>Твой путь начинается!</b>\n\n"
        f"Ты примкнул к фракции <b>{core_factions.FACTIONS[faction_key][1]}</b> и стартуешь в локации <b>{loc_name_full}</b>.\n\n"
        f"🎁 Получены стартовые бонусы:\n"
        f"• Репутация: <b>+50</b> (звание «Знакомый»)\n"
        f"• Бонусы: <b>{bonus_desc}</b>\n\n"
        f"<i>Удачи в Теневых Землях! Нажмите кнопку ниже, чтобы продолжить путь...</i>",
        reply_markup=main_menu_keyboard(has_character=True),
        image_url=FACTION_IMAGES.get(faction_key),
    )
    await callback.answer("Герой успешно создан!", show_alert=True)
