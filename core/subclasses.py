"""Специализации героев: серверная часть.

Каталог подклассов общий для обоих стеков и живёт в
`engine/subclasses.py`. Здесь только реэкспорт.
"""
from engine.subclasses import (  # noqa: F401
    SUBCLASS_MIN_LEVEL,
    SUBCLASSES,
    choose_subclass,
    get_available_subclasses,
    subclass_bonuses,
)
