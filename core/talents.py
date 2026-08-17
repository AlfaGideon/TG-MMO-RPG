"""Звёздное древо созвездий: серверная часть.

Каталог и логика — общие для обоих стеков и живут в `engine/talents.py`
(единственный источник правды). Здесь только реэкспорт привычных имён.
"""
from engine.talents import (  # noqa: F401
    LEVELS_PER_POINT,
    TALENT_STARS,
    get_unlocked_talents,
    points_for_level,
    talent_bonuses,
    unlock_talent,
)
