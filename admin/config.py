import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ADMIN_HOST: str = os.getenv("ADMIN_HOST", "0.0.0.0")
    ADMIN_PORT: int = int(os.getenv("ADMIN_PORT", "8000"))
    # Пустая строка вместо публичного дефолта: настоящий ключ подбирает
    # admin/auth.py (env → data/admin_secret.key → разовый).
    ADMIN_SECRET_KEY: str = os.getenv("ADMIN_SECRET_KEY", "")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/game.db")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
