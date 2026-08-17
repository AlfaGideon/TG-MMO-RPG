"""Титулы: серверная часть.

Каталог и вся логика — общие для обоих стеков и живут в
`engine/titles.py` (единственный источник правды). Здесь только
реэкспорт, чтобы серверный код и админка импортировали привычный путь.
"""
from engine.titles import (  # noqa: F401
    TITLES_CATALOG,
    get_unlocked_titles,
    set_active_title,
    title_bonus,
    title_line,
    unlock_title,
)
