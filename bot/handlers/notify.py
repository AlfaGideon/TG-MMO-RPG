"""🔕 Центр вестей: каналы напоминаний и тихие часы (IDEAS-new, 1.5).

Серверный паритет `engine/progress.notify_screen`. Хранилище — JSON-поле
`Character.prefs`; правила и дефолты общие с браузерным стеком в
`engine/notify.py` (переэкспорт `core/notify.py`).
"""
import json

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select

from bot.keyboards.inline import notify_keyboard
from bot.utils.edit import safe_edit_text
from core import notify as notify_common
from core.database import async_session
from core.models import Character, User

router = Router()


@router.callback_query(F.data == "notify")
async def notify_screen(callback: CallbackQuery):
    async with async_session() as session:
        ch = (await session.execute(
            select(Character).join(User, Character.user_id == User.id)
            .where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()
        if ch is None:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        prefs = notify_common.prefs_of(ch)
        lines = [
            "🔕 <b>Центр вестей</b>", "",
            "Личные напоминания приходят, когда сочтут нужным. Здесь ты "
            "решаешь, что не должно отвлекать.", "",
        ]
        for key, label in notify_common.CHANNELS:
            lines.append(f"{label}: {'✅ вкл' if prefs.get(key) else '⛔ выкл'}")
        quiet = prefs.get("quiet_enabled")
        lines += [
            "",
            f"Тихие часы ({prefs['quiet_start']}–{prefs['quiet_end']}): "
            f"{'🌙 вкл' if quiet else '☀️ выкл'}",
            "<i>В это время личные вести не приходят; глобальные анонсы о "
            "порталах остаются рассылкой.</i>",
        ]
        await safe_edit_text(callback, "\n".join(lines),
                             reply_markup=notify_keyboard(prefs))


@router.callback_query(F.data.startswith("notify_toggle:"))
async def notify_toggle(callback: CallbackQuery):
    key = callback.data.split(":", 1)[1]
    async with async_session() as session:
        ch = (await session.execute(
            select(Character).join(User, Character.user_id == User.id)
            .where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()
        if ch is None:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        _ok, prefs = notify_common.toggle(notify_common.prefs_of(ch), key)
        ch.prefs = json.dumps(prefs, ensure_ascii=False)
        await session.commit()
        await safe_edit_text(
            callback,
            _screen_text(prefs),
            reply_markup=notify_keyboard(prefs),
        )


@router.callback_query(F.data == "notify_quiet")
async def notify_quiet(callback: CallbackQuery):
    async with async_session() as session:
        ch = (await session.execute(
            select(Character).join(User, Character.user_id == User.id)
            .where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()
        if ch is None:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        prefs = notify_common.prefs_of(ch)
        prefs["quiet_enabled"] = not prefs.get("quiet_enabled", False)
        ch.prefs = json.dumps(prefs, ensure_ascii=False)
        await session.commit()
        await safe_edit_text(
            callback,
            _screen_text(prefs),
            reply_markup=notify_keyboard(prefs),
        )


def _screen_text(prefs: dict) -> str:
    lines = [
        "🔕 <b>Центр вестей</b>", "",
        "Личные напоминания приходят, когда сочтут нужным.", "",
    ]
    for key, label in notify_common.CHANNELS:
        lines.append(f"{label}: {'✅ вкл' if prefs.get(key) else '⛔ выкл'}")
    quiet = prefs.get("quiet_enabled")
    lines += [
        "",
        f"Тихие часы ({prefs['quiet_start']}–{prefs['quiet_end']}): "
        f"{'🌙 вкл' if quiet else '☀️ выкл'}",
    ]
    return "\n".join(lines)
