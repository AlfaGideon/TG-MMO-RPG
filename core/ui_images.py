"""Картинки экранов бота, управляемые из админки (таблица app_settings).

Заставка /start, картинка аукциона, шапка рейтинга и любые будущие экраны
(праздничные темы — Новый год, Хеллоуин) меняются из раздела админки
«🖼 Картинки» без правки кода: значение ключа `ui_image:<ключ>` — это
URL или путь /static/..., который умеет bot.utils.photos.get_photo_input.

Пока в настройке пусто — работает запасной файл из репозитория (DEFAULTS).
"""
from sqlalchemy import select

from core.models import AppSetting

DEFAULTS = {
    "welcome_ru": "/static/branding/start_ru.png",
    "welcome_en": "/static/branding/start_en.png",
    "auction": "/static/branding/auction.png",
    "leaderboard": "/static/branding/leaderboard.png",
}

# Человеческие подписи для раздела «Картинки» в админке.
TITLES = {
    "welcome_ru": "Заставка /start (RU)",
    "welcome_en": "Заставка /start (EN, резерв)",
    "auction": "Картинка аукциона",
    "leaderboard": "Картинка таблицы рейтинга",
}

_PREFIX = "ui_image:"


def setting_key(key: str) -> str:
    return f"{_PREFIX}{key}"


async def get(session, key: str):
    """Актуальная картинка экрана: настройка из БД → файл-запасной вариант.

    Пустая строка — картинки нет вовсе (экран откатится на текст).
    """
    result = await session.execute(
        select(AppSetting).where(AppSetting.key == setting_key(key)))
    setting = result.scalar_one_or_none()
    custom = (setting.value or "").strip() if setting else ""
    return custom or DEFAULTS.get(key, "")


async def set_value(session, key: str, value: str) -> None:
    """Записать/очистить настройку экрана (пустая строка = вернуть файл)."""
    result = await session.execute(
        select(AppSetting).where(AppSetting.key == setting_key(key)))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = value
    else:
        session.add(AppSetting(key=setting_key(key), value=value))
