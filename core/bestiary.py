"""Атлас монстров: серверная часть.

Логика общая для обоих стеков и живёт в `engine/bestiary.py`.
Здесь только реэкспорт привычных имён.
"""
from engine.bestiary import (  # noqa: F401
    bestiary_card_text,
    get_bestiary,
    get_mob_slayer_bonus,
    record_kill,
)
