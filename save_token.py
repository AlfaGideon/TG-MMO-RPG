"""Сохранить токен бота в базу (AppSetting.bot_token).

ВАЖНО: токен нельзя хранить в репозитории — файл лежит в публичном
git, а любой, кто увидит строку «<digits>:<34 символа>», получает полный
контроль над ботом (читает переписку всех игроков, пишет от их имени,
меняет настройки). Поэтому токен берётся из окружения или из аргумента.

Использование:
    BOT_TOKEN=123456:ABC-... python save_token.py
    python save_token.py 123456:ABC-...

Если токен уже где-то «засветился» — отзовите его у @BotFather
(/revoke) и выпустите новый; удаление строки из кода историю git не чинит.
"""
import asyncio
import os
import re
import sys

from sqlalchemy import select

from core.database import init_db, async_session
from core.models import AppSetting

TOKEN_RE = re.compile(r"^\d{6,}:[A-Za-z0-9_-]{30,}$")


async def save(token: str):
    await init_db()
    async with async_session() as session:
        result = await session.execute(select(AppSetting).where(AppSetting.key == 'bot_token'))
        s = result.scalar_one_or_none()
        if s:
            s.value = token
        else:
            s = AppSetting(key='bot_token', value=token)
            session.add(s)
        await session.commit()
    print('Token saved!')


def main():
    token = (sys.argv[1] if len(sys.argv) > 1 else os.getenv("BOT_TOKEN", "")).strip()
    if not token or not TOKEN_RE.match(token):
        print("Нужен настоящий токен: BOT_TOKEN=... python save_token.py "
              "(или аргументом). Секреты в репозиторий не кладём.")
        sys.exit(1)
    asyncio.run(save(token))


if __name__ == "__main__":
    main()
