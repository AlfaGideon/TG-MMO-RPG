"""Красивая книга помощи — по страницам, а не сплошное полотно."""

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from bot.utils.edit import safe_edit_text
from bot.keyboards.inline import help_menu_keyboard, back_to_help_keyboard

router = Router()

HELP_PAGES = [
    {
        "title": "📜 Основы",
        "text": """<b>📜 Книга помощи — страница 1/6</b>

<b>Основные команды:</b>
• <b>Профиль</b> — статы, экипировка, 3 валюты
• <b>Бой</b> — охота на монстров
• <b>Инвентарь</b> — вещи и крафт
• <b>Лавка</b> — покупка за бронзу/серебро/золото
• <b>Подземелье</b> — процедурные данжи

<b>💰 Три валюты (1:100)</b>
🟤 <b>Бронза</b> — мелочь
⚪ <b>Серебро</b> — средняя
🟡 <b>Золото</b> — высшая

Автоконвертация работает автоматически."""
    },
    {
        "title": "🆔 Уникальные предметы",
        "text": """<b>🆔 Уникальные предметы — страница 2/6</b>

У каждой вещи свой ID и свои статы.

<b>Значки происхождения:</b>
⚔️ — выбито в бою
📦 — из сундука
🕳 — из подземелья
🔨 — сковано
🏪 — куплено
🔁 — с аукциона
🌟 — единственное в мире

<b>📖 Летопись</b>
У именных вещей есть история — кто и когда добыл."""
    },
    {
        "title": "⚖️ Фракции",
        "text": """<b>⚖️ Фракционный баланс — страница 3/6</b>

Четыре силы связаны <b>по кругу вражды</b> и <b>по диагонали союза</b>:

🛡 Стража Погоста ↔ 💰 Гильдия падальщиков
💰 Гильдия ↔ 🌑 Культ Пожирателя
🌑 Культ ↔ ⚜️ Орден Рассвета
⚜️ Орден ↔ 🛡 Стража (союзники по диагонали)

Помогая одной — портишь репутацию у её врага по кругу."""
    },
    {
        "title": "🗺️ Мир",
        "text": """<b>🗺️ Мир и локации — страница 4/6</b>

<b>36 локаций</b> на карте 10×10:
• 4 угловых замка (25×25)
• 32 опасных тракта

Мир <b>бесшовный</b> — иди к краю локации, чтобы попасть в соседнюю.

<b>🗺 Карта</b> (в меню) — карта текущей локации и карта мира.
<b>🥾 В путь</b> — мгновенные путешествия между уже посещёнными безопасными локациями (у VIP — любыми).

<b>🕳 Подземелья</b>
Процедурные данжи открываются случайно по миру."""
    },
    {
        "title": "👑 VIP и обновления",
        "text": """<b>👑 VIP и обновления — страница 5/6</b>

<b>VIP даёт:</b>
+50% золота, +30% опыта, бонус лута, бесплатный аукцион, моментальные путешествия.

<b>🔄 Обновления</b>
Блок обновлений автоматически подтягивает изменения с GitHub.
Ручные записи добавляет только админ, когда сам внёс изменения."""
    },
    {
        "title": "💡 Советы",
        "text": """<b>💡 Советы — страница 6/6</b>

• Не выбрасывай хлам — он нужен для крафта
• Сундуки восстанавливаются
• Мир бесшовный — исследуй границы
• Пиши админу через бота
• Конвертация валюты 1:100 (🟤 бронза → ⚪ серебро → 🟡 золото)

<i>Удачи в Теневых Землях...</i>"""
    }
]


@router.callback_query(F.data == "help")
async def show_help_book(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_help_page(callback, 0)


@router.callback_query(F.data.startswith("help_page:"))
async def help_page(callback: CallbackQuery):
    page = int(callback.data.split(":")[1])
    await show_help_page(callback, page)


async def show_help_page(callback: CallbackQuery, page: int):
    page = max(0, min(page, len(HELP_PAGES) - 1))
    data = HELP_PAGES[page]

    text = f"{data['text']}\n\n<i>Страница {page + 1} из {len(HELP_PAGES)}</i>"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()

    nav = 0
    if page > 0:
        builder.button(text="◀️ Назад", callback_data=f"help_page:{page-1}")
        nav += 1
    if page < len(HELP_PAGES) - 1:
        builder.button(text="Вперёд ▶️", callback_data=f"help_page:{page+1}")
        nav += 1

    # Подразделы помощи: книга обновлений и место для идей игроков.
    # После перевода помощи в «книгу» эти кнопки потерялись — возвращаем.
    builder.button(text="📢 Обновления", callback_data="bot_updates")
    builder.button(text="💡 Идеи и пожелания", callback_data="bot_suggest")

    builder.button(text="◀️ В меню", callback_data="main_menu")

    rows = []
    if nav:
        rows.append(nav)
    rows.append(2)
    rows.append(1)
    builder.adjust(*rows)

    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()