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
    "splash_winter": "/static/branding/start_winter.png",
    "splash_spring": "/static/branding/start_spring.png",
    "splash_summer": "/static/branding/start_summer.png",
    "splash_autumn": "/static/branding/start_autumn.png",
}

# Человеческие подписи для раздела «Картинки» в админке.
TITLES = {
    "welcome_ru": "Заставка /start (RU)",
    "welcome_en": "Заставка /start (EN, резерв)",
    "auction": "Картинка аукциона",
    "leaderboard": "Картинка таблицы рейтинга",
    "splash_winter": "Сезонная заставка: зима ❄️",
    "splash_spring": "Сезонная заставка: весна 🌱",
    "splash_summer": "Сезонная заставка: лето ☀️",
    "splash_autumn": "Сезонная заставка: осень 🍂",
}

# Месяц → ключ сезонной заставки (метеорологические сезоны).
SEASON_BY_MONTH = {
    12: "splash_winter", 1: "splash_winter", 2: "splash_winter",
    3: "splash_spring", 4: "splash_spring", 5: "splash_spring",
    6: "splash_summer", 7: "splash_summer", 8: "splash_summer",
    9: "splash_autumn", 10: "splash_autumn", 11: "splash_autumn",
}

# Подпись-приправа под сезонную заставку на экране «Продолжить».
SEASON_FLAVOR = {
    "splash_winter": "❄️ В Теневых Землях зима — и снег золой ложится на руины.",
    "splash_spring": "🌱 В Теневых Землях весна — даже мёртвые деревья пускают почки.",
    "splash_summer": "☀️ В Теневых Землях лето — но затмение всё равно сильнее солнца.",
    "splash_autumn": "🍂 В Теневых Землях осень — туман стоит плотнее крепостных стен.",
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


def season_key(month: int | None = None) -> str:
    """Ключ сезонной заставки по месяцу (по умолчанию — текущему)."""
    import datetime

    if month is None:
        month = datetime.datetime.now().month
    return SEASON_BY_MONTH[month]


def _usable(url: str) -> bool:
    """Можно ли реально отдать картинку (файл на диске или http-ссылка)."""
    import os

    if not url:
        return False
    if url.startswith(("http://", "https://")):
        return True
    if url.startswith("/static/"):
        return os.path.isfile("admin" + url)
    return os.path.isfile(url)


async def seasonal_splash(session, month: int | None = None) -> str:
    """Заставка /start с подбором под сезон года.

    Порядок: настройка сезонного экрана из админки (праздничные темы —
    на Новый год или Хеллоуин вешают свою картинку поверх сезонной) →
    сезонный файл из репозитория → классическая заставка, если сезонной
    нет на диске.
    """
    key = season_key(month)
    url = await get(session, key)
    if not _usable(url):
        url = await get(session, "welcome_ru")
    return url
