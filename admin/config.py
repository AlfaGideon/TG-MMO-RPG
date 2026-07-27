import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ADMIN_HOST: str = os.getenv("ADMIN_HOST", "0.0.0.0")
    ADMIN_PORT: int = int(os.getenv("ADMIN_PORT", "8000"))
    ADMIN_SECRET_KEY: str = os.getenv("ADMIN_SECRET_KEY", "change-me")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/game.db")

    class Config:
        env_file = ".env"


settings = Settings()
