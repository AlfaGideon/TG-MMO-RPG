"""Красивая книга обновлений — компактные русские коммиты + книга для больших обновлений."""

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from core.database import async_session
from core.models import GameUpdate
from bot.utils.edit import safe_edit_text

router = Router()

# Примеры компактных русских обновлений (будут приходить из GitHub + ручные)
SAMPLE_UPDATES = [
    {
        "title": "v1.8 — Три валюты",
        "short": "Добавлена бронза, серебро и золото с конвертацией 1:100.",
        "full": [
            "• Введена трёхвалютная система",
            "• Бронза 🟤 → Серебро ⚪ → Золото 🟡",
            "• Автоконвертация при 100 единицах",
            "• Настройка курса в админке",
            "• Все награды, магазины и сундуки обновлены"
        ]
    },
    {
        "title": "v1.7 — 36 локаций",
        "short": "Мир расширен до 36 локаций (4 замка + 32 тракта).",
        "full": [
            "• 4 угловых замка 25×25",
            "• 32 опасных тракта по краям карты",
            "• Бесшовные переходы между всеми",
            "• Внутренние локации заменены"
        ]
    },
    {
        "title": "v1.6 — Книга помощи",
        "short": "Помощь теперь в виде красивой книги по страницам.",
        "full": [
            "• 6 страниц помощи вместо сплошного текста",
            "• Каждая страница оформлена отдельно",
            "• Удобная навигация стрелками"
        ]
    },
]


@router.callback_query(F.data == "bot_updates")
async def show_updates_book(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_updates_page(callback, 0)


@router.callback_query(F.data.startswith("updates_page:"))
async def updates_page(callback: CallbackQuery):
    page = int(callback.data.split(":")[1])
    await show_updates_page(callback, page)


async def show_updates_page(callback: CallbackQuery, page: int):
    async with async_session() as session:
        result = await session.execute(
            select(GameUpdate).order_by(GameUpdate.created_at.desc()).limit(20)
        )
        db_updates = result.scalars().all()

    # Объединяем GitHub + ручные + примеры
    all_updates = []
    for u in db_updates:
        all_updates.append({
            "title": u.title,
            "short": (u.became_text or "")[:120],
            "full": [u.became_text] if u.became_text else []
        })
    
    # Добавляем примеры если мало
    if len(all_updates) < 3:
        all_updates = SAMPLE_UPDATES + all_updates

    page = max(0, min(page, len(all_updates) - 1))
    update = all_updates[page]

    # Компактный вид или книга
    if len(update.get("full", [])) > 3:
        # Большое обновление — показываем как книгу
        text = f"📖 <b>{update['title']}</b>\n\n"
        for line in update["full"]:
            text += f"{line}\n"
        text += f"\n<i>Страница {page + 1} из {len(all_updates)}</i>"
    else:
        # Компактный коммит
        text = f"📝 <b>{update['title']}</b>\n\n{update['short']}\n\n<i>Обновление {page + 1} из {len(all_updates)}</i>"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()

    nav = 0
    if page > 0:
        builder.button(text="◀️ Назад", callback_data=f"updates_page:{page-1}")
        nav += 1
    if page < len(all_updates) - 1:
        builder.button(text="Вперёд ▶️", callback_data=f"updates_page:{page+1}")
        nav += 1

    # Книга обновлений — подраздел помощи: даём путь обратно к ней.
    builder.button(text="❓ К помощи", callback_data="help")
    builder.button(text="◀️ В меню", callback_data="main_menu")

    rows = []
    if nav:
        rows.append(nav)
    rows.append(2)
    builder.adjust(*rows)

    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()