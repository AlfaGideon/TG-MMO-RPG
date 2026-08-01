"""Автоматическая загрузка обновлений с GitHub (не из админки)."""

import httpx
from datetime import datetime
from core.database import async_session
from core.models import GameUpdate
from sqlalchemy import select

GITHUB_REPO = "AlfaGideon/TG-MMO-RPG"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/commits?per_page=10"


async def fetch_github_updates():
    """Получает последние коммиты с GitHub и добавляет как обновления."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(GITHUB_API)
            if resp.status_code != 200:
                return 0

            commits = resp.json()
            added = 0

            async with async_session() as session:
                for commit in commits:
                    sha = commit["sha"][:7]
                    message = commit["commit"]["message"].split("\n")[0][:200]
                    date = commit["commit"]["author"]["date"]

                    # Проверяем, есть ли уже такое обновление
                    existing = await session.scalar(
                        select(GameUpdate).where(GameUpdate.title.contains(sha))
                    )
                    if existing:
                        continue

                    update = GameUpdate(
                        title=f"🔄 GitHub: {sha}",
                        change_type="change",
                        was_text="",
                        became_text=message,
                        created_at=datetime.fromisoformat(date.replace("Z", "+00:00"))
                    )
                    session.add(update)
                    added += 1

                await session.commit()
            return added
    except Exception:
        return 0
