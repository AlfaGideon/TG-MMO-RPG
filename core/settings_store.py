"""Доступ к настройкам приложения (таблица app_settings).

Отдельный модуль, чтобы и бот, и админка читали одни и те же значения
без циклических импортов.
"""
import os

from sqlalchemy import select

from core.database import async_session
from core.models import AppSetting

PANEL_URL_KEY = "panel_url"


def normalize_url(raw: str) -> str:
    """Приводит введённый адрес к виду https://host[/path] без хвостового слэша."""
    url = (raw or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


async def get_setting(key: str, default: str = "") -> str:
    async with async_session() as session:
        result = await session.execute(
            select(AppSetting).where(AppSetting.key == key)
        )
        row = result.scalar_one_or_none()
    return row.value.strip() if row and row.value else default


async def set_setting(key: str, value: str) -> None:
    async with async_session() as session:
        result = await session.execute(
            select(AppSetting).where(AppSetting.key == key)
        )
        row = result.scalar_one_or_none()
        if row:
            row.value = value
        else:
            session.add(AppSetting(key=key, value=value))
        await session.commit()


async def get_panel_url() -> str:
    """Адрес админки: сначала из настроек, потом из переменных окружения."""
    saved = await get_setting(PANEL_URL_KEY)
    if saved:
        return normalize_url(saved)
    env = os.getenv("PUBLIC_URL") or os.getenv("ADMIN_PUBLIC_URL") or ""
    return normalize_url(env)


async def set_panel_url(value: str) -> str:
    url = normalize_url(value)
    await set_setting(PANEL_URL_KEY, url)
    return url


def build_login_url(base: str, telegram_id: int) -> str:
    """Готовая ссылка входа для инлайн-кнопки. Пусто, если адрес не задан."""
    base = normalize_url(base)
    if not base:
        return ""
    return f"{base}/admin-login?uid={telegram_id}"
