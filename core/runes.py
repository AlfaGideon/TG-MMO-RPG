"""Руны и рунические слова: серверная часть.

Каталоги и логика вставки — общие для обоих стеков и живут в
`engine/runes.py`. Здесь только реэкспорт привычных имён.
"""
from engine.runes import (  # noqa: F401
    RUNES,
    RUNEWORDS,
    SOCKETS,
    check_runeword,
    insert_rune,
    rune_icon,
    socket_line,
)
