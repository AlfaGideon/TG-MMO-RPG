from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from core import magic
from core.classes import get_class
from core.database import async_session
from core.stats import combat_stats
from core.vip import is_vip_active, offline_protected
from core.models import User, Character, Battle
from core.enums import BattleResult
from bot.keyboards.inline import (leaderboard_keyboard, main_menu_keyboard,
                                  profile_book_keyboard)
from bot.utils.texts import PROFILE_PAGES, profile_page_text
from bot.utils.photos import send_or_edit_photo
from bot.utils.edit import safe_edit_text

router = Router()


async def _profile_extra(session, character):
    """Цифры для разворотов «Снаряжение» и «Путь»."""
    from core.models import InventoryItem, VisitedCell

    bag = await session.scalar(
        select(func.count(InventoryItem.id))
        .where(InventoryItem.character_id == character.id)
        .where(InventoryItem.in_stash == False)  # noqa: E712
    ) or 0
    stash = await session.scalar(
        select(func.count(InventoryItem.id))
        .where(InventoryItem.character_id == character.id)
        .where(InventoryItem.in_stash == True)  # noqa: E712
    ) or 0
    visited = await session.scalar(
        select(func.count(VisitedCell.id))
        .where(VisitedCell.character_id == character.id)
    ) or 0
    locations_seen = await session.scalar(
        select(func.count(func.distinct(VisitedCell.location_id)))
        .where(VisitedCell.character_id == character.id)
    ) or 0
    victories = await session.scalar(
        select(func.count(Battle.id))
        .where(Battle.character_id == character.id)
        .where(Battle.result == BattleResult.VICTORY)
    ) or 0
    return {
        "bag_count": bag, "stash_count": stash, "visited": visited,
        "locations_seen": locations_seen, "victories": victories,
    }


async def _show_profile(callback: CallbackQuery, page: int = 0):
    """Профиль как книга: короткие развороты вместо простыни текста."""
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
        affinities = await magic.get_affinities(session, character.id)
        extra = await _profile_extra(session, character)

        total = len(PROFILE_PAGES)
        page = max(0, min(page, total - 1))
        text = profile_page_text(character, page, cls_def, stats, affinities,
                                 extra)

        await send_or_edit_photo(
            callback,
            text,
            reply_markup=profile_book_keyboard(
                page, total, [title for _, title in PROFILE_PAGES]),
            image_url=character.image_url,
        )


@router.callback_query(F.data == "profile")
async def profile(callback: CallbackQuery):
    await _show_profile(callback, 0)


@router.callback_query(F.data.startswith("profile_page:"))
async def profile_page(callback: CallbackQuery):
    await _show_profile(callback, int(callback.data.split(":")[1]))


@router.callback_query(F.data == "leaderboard")
async def leaderboard(callback: CallbackQuery):
    await safe_edit_text(callback, "🏆 <b>Доска почёта</b>\n\nВыбери категорию:",
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

    await safe_edit_text(callback, "\n".join(lines),
        reply_markup=leaderboard_keyboard(),
        parse_mode="HTML",
    )
