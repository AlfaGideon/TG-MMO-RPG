"""
Broadcast helpers: send a message (optionally with a themed image) to all
registered players, and detect/notify players whose in-progress action was
interrupted by a server restart (deploy, GitHub update, etc).
"""
import logging
import os

from sqlalchemy import select

from core.database import async_session
from core.models import User, Character, Cell, DungeonRun

logger = logging.getLogger(__name__)


async def broadcast_to_all(bot, text: str, image_path: str | None = None, reply_markup=None):
    """Sends a text (optionally with a photo) to every known Telegram user.
    `image_path` may be a local workspace path or an http(s) URL. Failures for
    individual users (blocked bot, etc) are swallowed so one bad chat doesn't
    stop the rest of the broadcast."""
    if bot is None:
        return 0

    async with async_session() as session:
        result = await session.execute(select(User.telegram_id))
        telegram_ids = [row[0] for row in result.all()]

    sent = 0
    photo_input = None
    if image_path:
        if image_path.startswith("http://") or image_path.startswith("https://"):
            photo_input = image_path
        elif os.path.exists(image_path):
            from aiogram.types import FSInputFile
            photo_input = FSInputFile(image_path)

    for telegram_id in telegram_ids:
        try:
            if photo_input:
                await bot.send_photo(
                    chat_id=telegram_id,
                    photo=photo_input,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            else:
                await bot.send_message(
                    chat_id=telegram_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            sent += 1
        except Exception as e:
            logger.debug(f"broadcast failed for {telegram_id}: {e}")

    return sent


async def notify_dungeon_portal_opened(bot, location_name: str, x: int, y: int, floor: int,
                                        template_name: str, image_url: str | None = None):
    """Announces a freshly-opened dungeon portal to every player."""
    floor_hint = f" (этаж {floor})" if floor else ""
    text = (
        "🌀 <b>Портал разорвал завесу мира!</b>\n\n"
        f"Где-то в <b>{location_name}</b>{floor_hint} на клетке <code>[{x},{y}]</code> "
        f"открылось подземелье «<b>{template_name}</b>».\n\n"
        "Дойди до этой клетки и войди внутрь, пока портал не закрылся..."
    )
    image_path = image_url.strip() if image_url and image_url.strip() else "admin/static/notifications/dungeon_portal.jpg"
    return await broadcast_to_all(bot, text, image_path)


async def notify_dungeon_portal_closed(bot, template_name: str):
    """Announces that a dungeon portal has sealed shut and no longer accepts
    new adventurers (those already inside are unaffected)."""
    text = (
        "🕳 <b>Портал начал закрываться...</b>\n\n"
        f"Подземелье «<b>{template_name}</b>» больше не принимает новых искателей — "
        "трещина в завесе мира затягивается.\n\n"
        "<i>Те, кто уже внутри, могут продолжать путь до конца.</i>"
    )
    image_path = "admin/static/notifications/portal_closing.jpg"
    return await broadcast_to_all(bot, text, image_path)


async def notify_update_deployed(bot):
    """Announces that the game world just got a fresh update, in-theme."""
    text = (
        "📖 <b>Хроники изменились...</b>\n\n"
        "Древние силы перекроили Теневые Земли — мир только что обновился новой магией разработчиков.\n"
        "Сервер ненадолго уйдёт в перезагрузку, чтобы принять изменения.\n\n"
        "<i>Если что-то не ответит с первого раза — просто повтори действие через несколько секунд.</i>"
    )
    image_path = "admin/static/notifications/update_banner.jpg"
    return await broadcast_to_all(bot, text, image_path)


async def notify_resume_interrupted_actions(bot):
    """Called right after the bot (re)starts. Looks for players who very
    likely had something in progress when the server went down (a monster
    still standing on their current cell, or an active dungeon run) and
    politely asks them to repeat their last action."""
    if bot is None:
        return 0

    already_notified = set()
    notified = 0
    async with async_session() as session:
        # World combat: character is standing on a cell that still has a live mob
        # (the mob is only cleared from the cell on victory, so if it's still
        # there the fight was very likely interrupted mid-round).
        result = await session.execute(
            select(Character, User)
            .join(User, Character.user_id == User.id)
            .join(Cell, Character.cell_id == Cell.id)
            .where(Cell.mob_id.isnot(None))
        )
        rows = result.all()
        for character, user in rows:
            if user.telegram_id in already_notified:
                continue
            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=(
                        "⚠️ <b>Сервер только что перезапустился.</b>\n\n"
                        f"Похоже, твой бой на клетке был прерван, {character.name}. "
                        "Открой меню и нажми «⚔️ Атаковать» ещё раз, чтобы продолжить."
                    ),
                    parse_mode="HTML",
                )
                already_notified.add(user.telegram_id)
                notified += 1
            except Exception as e:
                logger.debug(f"resume notice failed for {user.telegram_id}: {e}")

        # Dungeon runs: active run exists, but any mid-combat state was in
        # memory and is now gone — ask them to re-engage if they were fighting.
        result = await session.execute(
            select(Character, User)
            .join(User, Character.user_id == User.id)
            .join(DungeonRun, DungeonRun.character_id == Character.id)
            .where(DungeonRun.is_active.is_(True))
        )
        rows = result.all()
        for character, user in rows:
            if user.telegram_id in already_notified:
                continue
            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=(
                        "⚠️ <b>Сервер только что перезапустился.</b>\n\n"
                        f"Ты всё ещё внутри подземелья, {character.name}. Если сражался с монстром — "
                        "открой «🗿 Подземелье» и нажми «⚔️ Атаковать» ещё раз, чтобы повторить действие."
                    ),
                    parse_mode="HTML",
                )
                already_notified.add(user.telegram_id)
                notified += 1
            except Exception as e:
                logger.debug(f"resume notice failed for {user.telegram_id}: {e}")

    return notified
