from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from core.classes import get_class
from core.database import async_session
from core.stats import combat_stats
from core.models import User, Character, Battle
from bot.keyboards.inline import main_menu_keyboard, leaderboard_keyboard
from bot.utils.texts import profile_text
from bot.utils.photos import send_or_edit_photo

router = Router()


@router.callback_query(F.data == "profile")
async def profile(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        result = await session.execute(
            select(Character)
            .where(Character.user_id == user.id)
            .options(
                selectinload(Character.location),
                selectinload(Character.cell),
                selectinload(Character.party),
            )
        )
        character = result.scalar_one_or_none()
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        cls_def = await get_class(session, character.character_class)
        stats = await combat_stats(session, character)

        await send_or_edit_photo(
            callback,
            profile_text(character, cls_def, stats),
            reply_markup=main_menu_keyboard(has_character=True),
            image_url=character.image_url,
        )


@router.callback_query(F.data == "leaderboard")
async def leaderboard(callback: CallbackQuery):
    await callback.message.edit_text(
        "🏆 <b>Доска почёта</b>\n\nВыбери категорию:",
        reply_markup=leaderboard_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("lb:"))
async def leaderboard_view(callback: CallbackQuery):
    sort_by = callback.data.split(":")[1]
    async with async_session() as session:
        if sort_by == "level":
            result = await session.execute(
                select(Character, User)
                .join(User, Character.user_id == User.id)
                .order_by(Character.level.desc(), Character.experience.desc())
                .limit(10)
            )
        else:
            result = await session.execute(
                select(Character, User)
                .join(User, Character.user_id == User.id)
                .order_by(Character.gold.desc())
                .limit(10)
            )
        rows = result.all()

    lines = [f"🏆 <b>Топ по {'уровню' if sort_by == 'level' else 'золоту'}</b>\n"]
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    for idx, (char, user) in enumerate(rows, 1):
        name = user.username or user.first_name or "Безымянный"
        val = char.level if sort_by == "level" else char.gold
        icon = "⭐" if sort_by == "level" else "🪙"
        lines.append(f"{medals[idx-1]} {name} — {val}{icon}")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=leaderboard_keyboard(),
        parse_mode="HTML",
    )
