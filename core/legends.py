"""Зал Славы: серверная часть.

Тексты и правило «рекорд фиксируется один раз» — общие для обоих стеков
и живут в `engine/legends.py`. Здесь остаётся хранение в таблице
`ServerRecord`; экран собирает общая `hall_text`.
"""
from datetime import datetime, timezone

from sqlalchemy import select

from engine.legends import hall_text as _hall_text
from core.models import Character, ServerRecord


def _now():
    return datetime.now(timezone.utc)


async def record_server_first(session, record_key: str, title: str,
                              character: Character | None = None, detail: str = "") -> bool:
    """Фиксирует историческое первопроходство на сервере.

    `character=None` — вехи без автора («пережитый» миром катаклизм):
    владельцем строки становится «Сервер». Имя героя в летопись пишется
    копией (`holder_character_name`), а не ссылкой, — удаление персонажа
    не вычёркивает рекорд из истории.
    """
    existing = await session.scalar(
        select(ServerRecord).where(ServerRecord.record_key == record_key)
    )
    if existing:
        return False

    rec = ServerRecord(
        record_key=record_key,
        title=title,
        holder_character_name=character.name if character else "Сервер",
        holder_character_id=character.id if character else None,
        detail=detail,
    )
    session.add(rec)
    await session.flush()
    return True


async def get_hall_of_legends(session) -> list[ServerRecord]:
    result = await session.execute(
        select(ServerRecord).order_by(ServerRecord.id.desc())
    )
    return result.scalars().all()


def hall_of_legends_text(records: list) -> str:
    """Экран Зала Славы — общая вёрстка для обоих стеков."""
    return _hall_text(records)
