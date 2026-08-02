"""Админ-раздел внутри бота: свои права и пароль от веб-панели.

Игрок, которому выдали доступ, видит кнопку «🛠 Админка» в меню — раньше
доступ существовал только в базе, и в боте его не было видно вообще.
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select

from core.database import async_session
from core.models import User
from core.settings_store import get_panel_url, build_miniapp_url
from admin import auth as webauth
from bot.keyboards.inline import admin_panel_keyboard, back_to_main_keyboard
from bot.utils.edit import safe_edit_text

router = Router()


async def miniapp_url(telegram_id: int) -> str:
    """Ссылка Mini App: панель открывается внутри Telegram без пароля.

    Адрес панели берётся из настроек (panel_url) — его автоматически
    заполняет Quick Tunnel при старте, либо админ вручную (Render и т.п.).
    Пустая строка → кнопки нет (панель локальная, публичного адреса нет).
    """
    return build_miniapp_url(await get_panel_url(), telegram_id)


async def _get_admin(telegram_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
    if not user or not user.is_web_admin:
        return None
    return user


def caps_text(user: User) -> str:
    granted = webauth.caps_for(user.web_admin_role, user.web_admin_caps)
    lines = [f"• {webauth.CAP_LABELS[k]}" for k in webauth.CAP_KEYS if k in granted]
    return "\n".join(lines) or "—"


@router.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    user = await _get_admin(callback.from_user.id)
    if not user:
        await callback.answer("У тебя нет доступа к админке.", show_alert=True)
        return

    rank = webauth.ROLE_LABELS.get(user.web_admin_role, user.web_admin_role or "—")
    await safe_edit_text(callback, "🛠 <b>Доступ администратора</b>\n\n"
        f"Ранг: <b>{rank}</b>\n"
        f"Логин: <code>{user.telegram_id}</code>\n\n"
        f"<b>Твои права:</b>\n{caps_text(user)}\n\n"
        "<i>Кнопка «🌐 Открыть панель» запускает панель прямо в Telegram — "
        "без пароля. Пароль остаётся запасным входом из браузера.</i>",
        reply_markup=admin_panel_keyboard(await miniapp_url(user.telegram_id)),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_password")
async def admin_password(callback: CallbackQuery):
    user = await _get_admin(callback.from_user.id)
    if not user:
        await callback.answer("У тебя нет доступа к админке.", show_alert=True)
        return

    if not user.web_admin_password:
        plain = webauth.generate_password()
        async with async_session() as session:
            fresh = await session.get(User, user.id)
            fresh.web_admin_password = plain
            fresh.web_admin_password_hash = webauth.hash_password(plain)
            await session.commit()
    else:
        plain = user.web_admin_password

    await safe_edit_text(callback, "🔑 <b>Доступ в веб-панель</b>\n\n"
        f"Логин: <code>{user.telegram_id}</code>\n"
        f"Пароль: <code>{plain}</code>\n\n"
        "<i>Нажми на пароль, чтобы скопировать. Никому его не передавай.\n"
        "Пароль нужен только для входа из браузера — из Telegram панель "
        "открывается без него.</i>",
        reply_markup=admin_panel_keyboard(await miniapp_url(user.telegram_id)),
        parse_mode="HTML",
    )
