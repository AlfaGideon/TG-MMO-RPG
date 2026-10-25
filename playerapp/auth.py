"""Аутентификация игрока: коды входа, Bearer-токены, Telegram initData.

Два равноценных пути входа, оба ведут к одному и тому же User:

1. **Код из бота** (standalone APK): игрок пишет боту /app, получает
   6-значный код и вводит его в приложении. Код одноразовый, живёт 10 минут.
2. **Mini App initData** (внутри Telegram): клиент присылает подписанную
   ботом строку, подпись проверяется HMAC-SHA256 тем же алгоритмом, что и
   вход в админку (admin/tgapp.py:validate_init_data).

Успешный вход обоих типов выдаёт Bearer-токен на 90 дней.
"""
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import async_session
from core.models import AppSetting, User
from playerapp.models import PlayerLoginCode, PlayerSession

CODE_TTL = timedelta(minutes=10)
SESSION_TTL = timedelta(days=90)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _naive_utc(dt: datetime) -> datetime:
    """SQLite-хранилище наивное: приводим aware-время к naive UTC."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


# ── Одноразовые коды ────────────────────────────────────────────────

async def issue_code(session: AsyncSession, telegram_id: int) -> str:
    """Создаёт свежий код входа, гася предыдущие неиспользованные."""
    await session.execute(
        update(PlayerLoginCode)
        .where(PlayerLoginCode.telegram_id == telegram_id)
        .where(PlayerLoginCode.used_at.is_(None))
        .values(used_at=_naive_utc(_now()))
    )
    # 6 цифр без неоднозначных 0/1 — удобно диктовать и вводить с телефона.
    code = "".join(secrets.choice("23456789") for _ in range(6))
    session.add(PlayerLoginCode(
        telegram_id=telegram_id,
        code=code,
        expires_at=_naive_utc(_now() + CODE_TTL),
    ))
    await session.commit()
    return code


async def consume_code(session: AsyncSession, code: str) -> User | None:
    """Обменивает одноразовый код на пользователя (помечая код использованным)."""
    code = (code or "").strip()
    if not code:
        return None
    row = await session.scalar(
        select(PlayerLoginCode)
        .where(PlayerLoginCode.code == code)
        .where(PlayerLoginCode.used_at.is_(None))
        .order_by(PlayerLoginCode.id.desc())
    )
    if row is None or row.expires_at < _naive_utc(_now()):
        return None
    user = await session.scalar(
        select(User).where(User.telegram_id == row.telegram_id)
    )
    if user is None:
        return None
    row.used_at = _naive_utc(_now())
    await session.commit()
    return user


# ── Bearer-сессии ───────────────────────────────────────────────────

def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


async def create_session(
    session: AsyncSession, user: User, source: str, user_agent: str | None
) -> str:
    """Выдаёт новый сырой Bearer-токен (в БД уезжает только его хэш)."""
    raw_token = secrets.token_urlsafe(32)
    session.add(PlayerSession(
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        source=source,
        user_agent=(user_agent or "")[:256],
        expires_at=_naive_utc(_now() + SESSION_TTL),
    ))
    await session.commit()
    return raw_token


async def user_for_token(session: AsyncSession, raw_token: str) -> User | None:
    if not raw_token:
        return None
    row = await session.scalar(
        select(PlayerSession)
        .where(PlayerSession.token_hash == _hash_token(raw_token))
    )
    if row is None or row.revoked or row.expires_at < _naive_utc(_now()):
        return None
    user = await session.get(User, row.user_id)
    if user is None or user.is_banned:
        return None
    row.last_used_at = _naive_utc(_now())
    await session.commit()
    return user


async def current_user(
    authorization: str | None = Header(default=None),
) -> User:
    """FastAPI-зависимость: требует валидный `Authorization: Bearer …`."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Нужен вход в приложение")
    token = authorization[len("Bearer "):].strip()
    async with async_session() as session:
        user = await user_for_token(session, token)
    if user is None:
        raise HTTPException(status_code=401, detail="Сессия истекла, войдите заново")
    return user


# ── Telegram Mini App initData ──────────────────────────────────────

async def _bot_token() -> str:
    """Тот же токен, что использует бот: настройка панели, иначе env."""
    try:
        async with async_session() as session:
            setting = await session.scalar(
                select(AppSetting).where(AppSetting.key == "bot_token")
            )
        if setting and setting.value and setting.value.strip():
            return setting.value.strip()
    except Exception:
        pass
    return os.getenv("BOT_TOKEN", "")


async def user_for_init_data(session: AsyncSession, init_data: str) -> User | None:
    """Проверяет подпись Telegram и находит (но не создаёт!) пользователя.

    Создание персонажа — осознанный сценарий бота с выбором класса и
    фракции; приложение лишь подключается к уже существующему аккаунту.
    """
    from admin.tgapp import validate_init_data

    data = validate_init_data(init_data, await _bot_token())
    if not data:
        return None
    tg_user = data["user"]
    return await session.scalar(
        select(User).where(User.telegram_id == tg_user["id"])
    )
