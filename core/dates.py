"""Единая точка работы со временем для серверного стека.

Колонки в `core/models.py` — `DateTime(timezone=True)`. SQLite возвращает
naive datetime, Postgres — aware: смешивание в Python-сравнениях даёт
TypeError (и тихо умирающие фоновые циклы в проде). Поэтому «сейчас»
всегда aware, а значения из БД прогоняем через `aware()`.
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Текущее время UTC (aware) — для записи и сравнений."""
    return datetime.now(timezone.utc)


def aware(dt):
    """Привести значение из БД к aware: SQLite отдаёт naive."""
    return dt if (dt is None or dt.tzinfo) else dt.replace(tzinfo=timezone.utc)
