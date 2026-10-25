"""Таблицы мобильного игрового приложения.

Импортируются из core/migrations.py, чтобы попасть в Base.metadata и
создаться через create_all вместе с остальными таблицами (тот же приём,
что у core/guilds.py и core/community.py).
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String,
    func,
)

from core.database import Base


class PlayerLoginCode(Base):
    """Одноразовый код входа, который бот выдаёт командой /app.

    Код живёт несколько минут, работает один раз. Нужен для входа в APK:
    у standalone-WebView нет Telegram-окружения, поэтому связка аккаунта
    выполняется через код, показанный в личном чате с ботом.
    """

    __tablename__ = "player_login_codes"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, nullable=False, index=True)
    code = Column(String(8), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)


class PlayerSession(Base):
    """Долгоживущая Bearer-сессия приложения.

    В базе храним только sha256 токена: утечка дампа БД не даёт готовых
    ключей доступа. Сам токен показывается клиенту один раз при выдаче.
    """

    __tablename__ = "player_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    # «telegram» — вход через Mini App initData, «code» — код из бота.
    source = Column(String(16), nullable=False, default="code")
    user_agent = Column(String(256), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False)
