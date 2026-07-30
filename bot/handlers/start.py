from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.database import async_session
from core.models import User, Character, Cell, AdminMessage, VisitedCell, PlayerSuggestion, GameUpdate
from bot.keyboards.inline import (
    main_menu_keyboard, class_select_keyboard, confirm_class_keyboard,
    back_to_main_keyboard, reroll_keyboard, help_menu_keyboard, back_to_help_keyboard,
)
from bot.utils.texts import WELCOME_TEXT, class_description_text, reroll_text
from bot.utils.photos import send_or_edit_photo
from core import magic, statroll
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

        text_lower = message.text.lower().strip()
        if text_lower.startswith("идея") or text_lower.startswith("idea"):
            # Extract the actual idea text
            idea_content = message.text
            for prefix in ["идея:", "идея", "idea:", "idea"]:
                if text_lower.startswith(prefix):
                    idea_content = message.text[len(prefix):].strip()
                    break
            
            if idea_content:
                result = await session.execute(
                    select(Character).where(Character.user_id == user.id)
                )
                character = result.scalar_one_or_none()
                if not character:
                    await message.answer("Сначала создай персонажа, чтобы предлагать идеи!")
                    return
                
                suggestion = PlayerSuggestion(
                    character_id=character.id,
                    text=idea_content,
                    status="pending"
                )
                session.add(suggestion)
                await session.commit()
                
                await message.answer(
                    "💡 <b>Твоё предложение успешно отправлено разработчикам!</b>\n\n"
                    "Мы взяли его на рассмотрение. Как только администратор изменит статус твоей идеи в панели управления, тебе придёт уведомление здесь в боте.\n"
                    "Спасибо за помощь в улучшении игры! 🤝",
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


@router.callback_query(F.data == "bot_updates")
async def bot_updates_handler(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(GameUpdate).order_by(GameUpdate.created_at.desc()).limit(15)
        )
        updates = result.scalars().all()

    if not updates:
        text = (
            "📢 <b>Обновления игры</b>\n\n"
            "Пока нет записанных обновлений. Следите за новостями в ближайшее время!"
        )
    else:
        text = "📢 <b>Последние обновления игры:</b>\n\n"
        for i, up in enumerate(updates, 1):
            date_str = up.created_at.strftime('%d.%m.%Y') if up.created_at else ''
            text += f"{i}. <b>{up.title}</b> ({date_str})\n"
            if up.change_type == "change":
                text += f"   ❌ <i>Было:</i> {up.was_text}\n"
                text += f"   ✅ <i>Стало:</i> {up.became_text}\n\n"
            else:
                text += f"   ⭐ {up.became_text}\n\n"

    await callback.message.edit_text(text, reply_markup=back_to_help_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "bot_suggest")
async def bot_suggest_handler(callback: CallbackQuery):
    text = (
        "💡 <b>Предложить идею по улучшению игры</b>\n\n"
        "Мы очень ценим твои отзывы и предложения!\n\n"
        "Чтобы твоя идея попала напрямую в раздел пожеланий в админ-панели, отправь её следующим сообщением, начав со слова <b>Идея</b>.\n\n"
        "<b>Пример:</b>\n"
        "<code>Идея Добавить больше редкого оружия во 2-ю локацию</code>"
    )
    await callback.message.edit_text(text, reply_markup=back_to_help_keyboard(), parse_mode="HTML")


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
            location_id=1,
            floor=0,
            cell_id=spawn_cell.id if spawn_cell else None,
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

        if spawn_cell:
            session.add(VisitedCell(
                character_id=character.id,
                location_id=1,
                floor=0,
                x=spawn_cell.x,
                y=spawn_cell.y,
            ))
        await session.commit()
        char_id = character.id

        # realtime — новый игрок
        try:
            from core.realtime import publish as rt_publish
            await rt_publish("player_joined", {
                "character_id": char_id,
                "name": character.name,
                "telegram_id": user.telegram_id,
                "class": character.character_class,
                "level": character.level,
                "location_id": character.location_id,
            })
        except Exception:
            pass

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
        await callback.message.edit_text(
            reroll_text(character, cls_def, base, rolled, affinities, final=True),
            reply_markup=main_menu_keyboard(has_character=True),
            parse_mode="HTML",
        )
        return

    await callback.message.edit_text(
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

    await callback.message.edit_text(
        reroll_text(character, cls_def, base, rolled, affinities, final=True),
        reply_markup=main_menu_keyboard(has_character=True),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "help")
async def help_handler(callback: CallbackQuery):
    text = (
        "📜 <b>Помощь и Информация по игре</b>\n\n"
        "<b>Основные команды:</b>\n"
        "• Профиль — статы, экипировка по слотам и золото\n"
        "• Бой — охота на монстров (осмотрись на клетке и ищи 👾)\n"
        "• Инвентарь — надеть, использовать, выбросить\n"
        "• Лавка — покупка снаряжения\n"
        "• Подземелье — процедурные данжи (соло)\n\n"
        "<b>🆔 Уникальные предметы:</b>\n"
        "У каждой вещи свой ID и свои статы — два одинаковых меча всё равно "
        "разные. Смотри «Качество»: чем выше процент, тем удачнее экземпляр.\n"
        "Значок перед ID говорит, откуда вещь: ⚔️ выбита в бою, 📦 из сундука, "
        "🕳 из подземелья, 🔨 скована, 🏪 куплена, 🔁 с аукциона, "
        "🎄 праздничная, 🌟 единственная в мире.\n\n"
        "<b>📖 История:</b>\n"
        "У именных вещей есть летопись — видно, кто её добыл и через сколько "
        "рук она прошла. Ресурсы истории не имеют.\n\n"
        "<b>⚖️ Аукцион:</b>\n"
        "Продавай вещи другим игрокам или сразу скупщику — он даст меньше, "
        "зато немедленно. Непроданный лот вернётся через сутки.\n\n"
        "<b>🔮 Магия:</b>\n"
        "Шесть школ: 🔥 огонь, ❄️ лёд, ⚡ гроза, 🌑 тьма, 🌿 природа, ✨ свет. "
        "Дар бросается при создании героя — от полного его отсутствия до двух "
        "школ сразу. Чем сильнее дар, тем мощнее «✨ Умение» в бою.\n\n"
        "<b>🔨 Ремесло:</b>\n"
        "Найди на карте кузнеца, алхимика или ювелира. Он скуёт вещь по рецепту "
        "из твоих материалов и заточит то, что уже носишь. Заточка растит статы, "
        "но при неудаче ресурсы сгорают.\n\n"
        "<b>👾 Монстры:</b>\n"
        "Мобы ходят по карте и восстанавливаются со временем. Слабые могут "
        "забредать в опасные земли, а вот сильные к новичкам не заходят.\n\n"
        "<b>⚖️ Фракционный баланс:</b>\n"
        "Три фракции связаны по принципу «Камень-ножницы-бумага»:\n"
        "• 🛡️ <b>Стража Погоста</b> враждует с 💰 <b>Гильдией падальщиков</b>\n"
        "• 💰 <b>Гильдия падальщиков</b> враждует с 🌑 <b>Культом Пожирателя</b>\n"
        "• 🌑 <b>Культ Пожирателя</b> враждует с 🛡️ <b>Стражей Погоста</b>\n"
        "Помогая одной фракции, ты портишь репутацию у соперника, так что быть другом для всех не получится!\n\n"
        "<b>🛠️ Проделанная работа (Последние крупные обновления):</b>\n"
        "1. 🎒 <b>Защищенный карман (Stash):</b> Ценные вещи теперь можно прятать в карман. При гибели героя вещи из сумки остаются на месте смерти в виде надгробия (их можно вернуть в течение суток), а скрытые в кармане вещи всегда уцелевают с героем.\n"
        "2. 🕳️ <b>Процедурные подземелья (Dungeons):</b> Запущены глубокие опасные лабиринты. Порталы в них открываются случайно по всему миру. Внутри ждут сундуки, тайники и элитные враги.\n"
        "3. 🌋 <b>Мировые катаклизмы:</b> Реализованы случайные и управляемые администраторами события (землетрясения, туманы, метеоритный дождь) и призывы грозных Мировых Боссов, победа над которыми приносит ценнейшую добычу всем участникам.\n"
        "4. 👑 <b>VIP-статус:</b> Реализована полноценная VIP-система. Владельцы VIP получают +50% золота, +30% опыта, бонус к качеству лута, бесплатный аукцион, расширенный карман и моментальные путешествия во все открытые земли.\n\n"
        "<b>Советы:</b>\n"
        "— Мир бесшовный: иди к краю локации, чтобы попасть в соседнюю\n"
        "— Отдыхай, чтобы восстановить здоровье\n"
        "— Не выбрасывай хлам: лом, шкуры и кости нужны для крафта\n"
        "— Сундуки со временем наполняются заново\n"
        "— Пиши админу простым сообщением в бот\n\n"
        "<i>Удачи в Теневых Землях...</i>"
    )
    await callback.message.edit_text(text, reply_markup=help_menu_keyboard(), parse_mode="HTML")
