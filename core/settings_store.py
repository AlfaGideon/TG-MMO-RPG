"""Доступ к настройкам приложения (таблица app_settings).

Отдельный модуль, чтобы и бот, и админка читали одни и те же значения
без циклических импортов.
"""
import logging
import os
import uuid
from urllib.parse import urlparse

from sqlalchemy import select

from core.database import async_session
from core.models import AppSetting

PANEL_URL_KEY = "panel_url"

logger = logging.getLogger("settings")

# Метка запущенной копии сервера. По ней /health отвечает, «свой» ли это
# процесс: адрес Quick Tunnel от прошлого запуска (или чужой орфан
# cloudflared) отдаст другую метку, и мы не разошлём мёртвую ссылку.
INSTANCE_ID = uuid.uuid4().hex

# Managed platforms already know the public HTTPS address of a service.  Using
# it is much more reliable than a temporary Quick Tunnel: the latter is
# intentionally ephemeral and may yield Cloudflare 1033 after a restart.
PUBLIC_URL_ENV_KEYS = (
    "PUBLIC_URL",
    "ADMIN_PUBLIC_URL",
    "RENDER_EXTERNAL_URL",
)

# Адрес Quick Tunnel, поднятого ИМЕННО ЭТИМ процессом, и признак того, что
# процесс вообще управляет туннелем. Нужны, чтобы бот никогда не выдал ссылку
# перезапуска отдаёт страницу Cloudflare 1033.
_active_tunnel_url = ""
_tunnel_managed = False


def normalize_url(raw: str) -> str:
    """Приводит введённый адрес к виду https://host[/path] без хвостового слэша."""
    url = (raw or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def is_temporary_tunnel_url(value: str) -> bool:
    """Проверяет, является ли адрес временным туннелем (trycloudflare.com).
    
    Такие адреса не должны использоваться - они эфемерные и не работают
    после перезапуска. Возвращает True для любых trycloudflare.com доменов.
    """
    if not value:
        return False
    normalized = value.lower()
    return "trycloudflare.com" in normalized


def set_active_tunnel_url(url: str) -> None:
    """Запомнить адрес туннеля, который подняла именно эта копия сервера."""
    global _active_tunnel_url
    _active_tunnel_url = normalize_url(url)


def active_tunnel_url() -> str:
    # Туннельная схема удалена.
    return ""


def mark_tunnel_managed(flag: bool = True) -> None:
    # Туннельная схема удалена.
    global _tunnel_managed
    _tunnel_managed = False


def tunnel_is_managed() -> bool:
    return False


def is_stale_tunnel_url(value: str) -> bool:
    """Проверяет, является ли адрес устаревшим туннелем.
    
    Любой trycloudflare.com адрес считается устаревшим - они не работают
    после перезапуска и должны быть удалены из настроек.
    """
    return is_temporary_tunnel_url(value)


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
    """Адрес админки для кнопок бота.

    Порядок: живой Quick Tunnel этого процесса → сохранённый вручную адрес →
    домен хостинга из окружения.

    Отдельная защита от главной ловушки: в БД мог остаться
    рестарта cloudflared выдаёт новый домен, а старый отвечает ошибкой 1033),
    поэтому мы его игнорируем и заодно вычищаем из настроек — иначе бот
    продолжает рассылать старую ссылку.
    """
    if _active_tunnel_url:
        return _active_tunnel_url

    saved = normalize_url(await get_setting(PANEL_URL_KEY))
    if saved and is_stale_tunnel_url(saved):
        logger.info(
            f"Игнорирую устаревший адрес Quick Tunnel из настроек ({saved}) — "
            "он остался от прошлого запуска сервера."
        )
        try:
            await set_setting(PANEL_URL_KEY, "")
        except Exception:
            pass
        saved = ""
    if saved:
        return saved
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
