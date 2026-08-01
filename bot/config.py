import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    # Optional Telegram Bot API proxy. Useful when Telegram is blocked by ISP.
    # Examples:
    #   socks5://127.0.0.1:9050  - system Tor service
    #   socks5://127.0.0.1:9150  - Tor Browser
    TELEGRAM_PROXY_URL: str = os.getenv(
        "TELEGRAM_PROXY_URL",
        os.getenv("BOT_PROXY_URL", ""),
    )
    ADMIN_IDS: list[int] = [
        int(x.strip())
        for x in os.getenv("ADMIN_IDS", "").split(",")
        if x.strip().isdigit()
    ]

    class Config:
        env_file = ".env"


settings = Settings()
