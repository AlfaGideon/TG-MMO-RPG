"""Доступ к настройкам приложения (таблица app_settings).

Отдельный модуль, чтобы и бот, и админка читали одни и те же значения
без циклических импортов.
"""
import os

from sqlalchemy import select

from core.database import async_session
from core.models import AppSetting

PANEL_URL_KEY = "panel_url"

# Managed platforms already know the public HTTPS address of a service.  Using
# it is much more reliable than a temporary Quick Tunnel: the latter is
# intentionally ephemeral and may yield Cloudflare 1033 after a restart.
PUBLIC_URL_ENV_KEYS = (
    "PUBLIC_URL",
    "ADMIN_PUBLIC_URL",
    "RENDER_EXTERNAL_URL",
)


def normalize_url(raw: str) -> str:
    """Приводит введённый адрес к виду https://host[/path] без хвостового слэша."""
    url = (raw or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def platform_public_url() -> str:
    """Вернуть HTTPS-адрес, который даёт хостинг, если он известен.

    Render exposes ``RENDER_EXTERNAL_URL``. Replit exposes either a single
    ``REPLIT_DEV_DOMAIN`` or a comma-separated ``REPLIT_DOMAINS`` list. This
    fallback deliberately lives here, so the bot, panel and tunnel code make
    exactly the same URL choice.
    """
    for key in PUBLIC_URL_ENV_KEYS:
        value = normalize_url(os.getenv(key, ""))
        if value:
            return value

    # Replit may put several domains into REPLIT_DOMAINS. The first is the
    # canonical HTTPS domain; the remaining values are aliases.
    replit = os.getenv("REPLIT_DEV_DOMAIN", "") or os.getenv("REPLIT_DOMAINS", "")
    if replit:
        return normalize_url(replit.split(",", 1)[0])
    return ""


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
    """Адрес админки: сохранённый вручную, затем адрес хостинга из env."""
    saved = await get_setting(PANEL_URL_KEY)
    if saved:
        return normalize_url(saved)
    return platform_public_url()


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


def build_miniapp_url(base: str, telegram_id: int) -> str:
    """Ссылка Mini App для кнопки web_app (вход по подписи Telegram).

    Пусто, если адрес не задан. Отличается от build_login_url: /tgapp
    открывается мини-приложением и пускает без пароля, /admin-login —
    классическая страница для браузера с логином и паролем.
    """
    base = normalize_url(base)
    if not base:
        return ""
    return f"{base}/tgapp?uid={telegram_id}"
