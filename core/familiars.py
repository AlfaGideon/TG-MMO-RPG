"""Фамильяры: серверная часть.

Каталог спутников общий для обоих стеков и живёт в
`engine/familiars.py`. Здесь только реэкспорт.
"""
from engine.familiars import (  # noqa: F401
    FAMILIARS,
    familiar_bonuses,
    familiar_card_text,
    get_familiar,
    set_familiar,
)
