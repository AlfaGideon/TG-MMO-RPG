from html import escape

from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from core import magic, statpoints
from core.classes import get_class
from core.database import async_session
from core.stats import combat_stats
from engine.stats import calculate_gear_score, get_russian_stat_name
from core.vip import is_vip_active, offline_protected
from core.models import User, Character, Battle
from core.enums import BattleResult
from bot.keyboards.inline import (leaderboard_keyboard, main_menu_keyboard,
                                  profile_book_keyboard, stat_alloc_keyboard)
from bot.utils.texts import PROFILE_PAGES, profile_page_text
from bot.utils.photos import send_or_edit_photo
from bot.utils.edit import safe_edit_text

router = Router()


async def _profile_extra(session, character):
    """Цифры для разворотов «Снаряжение» и «Путь»."""
    from core.models import InventoryItem, VisitedCell, AppSetting
    from core import factions as core_factions

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

    my_faction = core_factions.allegiance(character)
    is_leader = False
    if my_faction:
        leader_row = await session.scalar(
            select(AppSetting).where(AppSetting.key == f"faction_leader_{my_faction}")
        )
        if leader_row and leader_row.value and int(leader_row.value) == character.id:
            is_leader = True

    return {
        "bag_count": bag, "stash_count": stash, "visited": visited,
        "locations_seen": locations_seen, "victories": victories,
        "is_leader": is_leader,
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
        extra["allocated"] = statpoints.load_allocated(character)
        extra["free_points"] = statpoints.free_points(character)
        text = profile_page_text(character, page, cls_def, stats, affinities,
                                 extra)

        # Кнопка распределения очков живёт на странице «📊 Характеристики».
        stats_page = next(
            (i for i, (k, _t) in enumerate(PROFILE_PAGES) if k == "stats"), None)
        free = extra["free_points"] if page == stats_page else None

        await send_or_edit_photo(
            callback,
            text,
            reply_markup=profile_book_keyboard(
                page, total, [title for _, title in PROFILE_PAGES],
                free_points=free),
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
    from core import factions as core_factions

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
            # Сортировка по общей ценности в бронзе (1⚪=100🟤, 1🟡=100⚪) —
            # иначе герой с 90⚪ проигрывал бы герою с 1🟡 и пустыми карманами.
            wealth = (Character.gold * 10000 + Character.silver * 100
                      + Character.bronze)
            result = await session.execute(
                select(Character, User)
                .join(User, Character.user_id == User.id)
                .order_by(wealth.desc())
                .limit(10)
            )
        rows = result.all()

    lines = [f"🏆 <b>Топ по {'уровню' if sort_by == 'level' else 'золоту'}</b>\n"]
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    for idx, (char, user) in enumerate(rows, 1):
        # В рейтинге — значок фракции и имя из Telegram (отображаемое имя),
        # а не технический тег @username: по нему людей всё равно не знают.
        display = " ".join(
            part for part in (user.first_name or "", user.last_name or "")
            if part).strip()
        if not display:
            display = char.name or "Безымянный"
        display = escape(display)
        faction_key = (getattr(char, "faction", "") or
                       core_factions.allegiance(char))
        faction_icon = ""
        if faction_key in core_factions.FACTIONS:
            f_icon = core_factions.FACTIONS[faction_key][0]
            faction_icon = f"{f_icon} "
        if sort_by == "level":
            val = char.level
            icon = "⭐"
        else:
            # Show 3 currencies
            b = getattr(char, "bronze", 0)
            s = getattr(char, "silver", 0)
            g = getattr(char, "gold", 0)
            val = f"{b}🟤{s}⚪{g}🟡"
            icon = ""
        lines.append(f"{medals[idx-1]} {faction_icon}{display} — {val}{icon}")

    await safe_edit_text(callback, "\n".join(lines),
        reply_markup=leaderboard_keyboard(),
        parse_mode="HTML",
    )


# ── распределение очков характеристик ───────────────────────

def _stat_alloc_text(character) -> str:
    """Экран «🎯 Очки характеристик»: все статы с разложением на базу и
    вложенные очки, легенда эффектов."""
    alloc = statpoints.load_allocated(character)
    free = statpoints.free_points(character)

    lines = [
        "🎯 <b>Распределение характеристик</b>",
        "",
        f"Свободных очков: <b>{free}</b>",
        "",
    ]
    for skey in statpoints.ALLOCATABLE:
        emoji, label = statpoints.STAT_LABELS[skey]
        total_v = int(getattr(character, skey, 0) or 0)
        invested = alloc.get(skey, 0)
        base_v = total_v - invested
        lines.append(
            f"{emoji} {label}: <b>{total_v}</b> "
            f"<i>(база {base_v} + вложено {invested})</i>")
    lines += [
        "",
        "<b>Что даёт очко:</b>",
        f"🛡 Выносливость — +{statpoints.HP_PER_ENDURANCE} ❤️ HP",
        f"🧠 Интеллект — +{statpoints.MP_PER_INTELLIGENCE} 💙 MP",
        "💪 Сила, 🏃 Ловкость, 🍀 Удача — +1 к стату",
        "",
        "<i>➕ вложить очко · ➖ снять вложенное обратно. Базовые "
        "(стартовые) характеристики неизменны. Очки выдаются с уровнями.</i>",
    ]
    return "\n".join(lines)


def _stat_alloc_values(character) -> dict:
    alloc = statpoints.load_allocated(character)
    return {
        skey: (int(getattr(character, skey, 0) or 0), alloc.get(skey, 0))
        for skey in statpoints.ALLOCATABLE
    }


async def _stat_alloc_character(callback: CallbackQuery, session):
    result = await session.execute(
        select(User).where(User.telegram_id == callback.from_user.id))
    user = result.scalar_one_or_none()
    if not user:
        await callback.answer("Сначала создай персонажа!", show_alert=True)
        return None
    character = (await session.execute(
        select(Character).where(Character.user_id == user.id)
    )).scalar_one_or_none()
    if not character:
        await callback.answer("Сначала создай персонажа!", show_alert=True)
        return None
    return character


async def _show_stat_alloc(callback: CallbackQuery):
    async with async_session() as session:
        character = await _stat_alloc_character(callback, session)
        if character is None:
            return
        await safe_edit_text(
            callback,
            _stat_alloc_text(character),
            reply_markup=stat_alloc_keyboard(
                _stat_alloc_values(character),
                statpoints.free_points(character)),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "stat_alloc")
async def stat_alloc_menu(callback: CallbackQuery):
    await _show_stat_alloc(callback)


@router.callback_query(F.data == "profile_stats_page")
async def profile_stats_page(callback: CallbackQuery):
    stats_page = next(
        (i for i, (k, _t) in enumerate(PROFILE_PAGES) if k == "stats"), 0)
    await _show_profile(callback, stats_page)


@router.callback_query(F.data.startswith("stat_add:"))
async def stat_add(callback: CallbackQuery):
    skey = callback.data.split(":")[1]
    async with async_session() as session:
        character = await _stat_alloc_character(callback, session)
        if character is None:
            return
        if not statpoints.allocate(character, skey):
            await callback.answer(
                "Нет свободных очков. Они выдаются с новыми уровнями.",
                show_alert=True)
            return
        await session.commit()
        emoji, label = statpoints.STAT_LABELS[skey]
        await safe_edit_text(
            callback,
            _stat_alloc_text(character),
            reply_markup=stat_alloc_keyboard(
                _stat_alloc_values(character),
                statpoints.free_points(character)),
            parse_mode="HTML",
        )
        effect = statpoints.STAT_EFFECTS[skey]
        await callback.answer(f"{emoji} {label}: {effect}")


@router.callback_query(F.data.startswith("stat_del:"))
async def stat_del(callback: CallbackQuery):
    skey = callback.data.split(":")[1]
    async with async_session() as session:
        character = await _stat_alloc_character(callback, session)
        if character is None:
            return
        if not statpoints.deallocate(character, skey):
            await callback.answer(
                "Снять можно только вложенные очки — база неизменна.",
                show_alert=True)
            return
        await session.commit()
        emoji, label = statpoints.STAT_LABELS[skey]
        await safe_edit_text(
            callback,
            _stat_alloc_text(character),
            reply_markup=stat_alloc_keyboard(
                _stat_alloc_values(character),
                statpoints.free_points(character)),
            parse_mode="HTML",
        )
        await callback.answer(f"{emoji} Очко снято и вернулось в резерв.")


@router.callback_query(F.data.startswith("stat_hint:"))
async def stat_hint(callback: CallbackQuery):
    skey = callback.data.split(":")[1]
    if skey in statpoints.ALLOCATABLE:
        await callback.answer(
            f"Следующее очко: {statpoints.STAT_EFFECTS[skey]}",
            show_alert=True)
    else:
        await callback.answer()
