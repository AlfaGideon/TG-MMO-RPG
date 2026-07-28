"""Случайные стартовые характеристики и их перекат.

Герой больше не рождается с одинаковым для всех классов набором: статы
катаются от базовых значений класса в диапазоне −10 % … +20 %. При
создании даётся 10 попыток переката — можно жать «ещё раз», пока не
устроит результат. Принял бросок или потратил попытки — статы фиксируются.
"""
import math
import random

# Разброс от базового значения класса
MIN_FACTOR = 0.90   # −10 %
MAX_FACTOR = 1.20   # +20 %

# Сколько раз можно перекатить при создании героя
DEFAULT_REROLLS = 10

# Что именно катается
ROLLED_STATS = (
    "strength", "agility", "intelligence", "endurance", "luck",
    "max_hp", "max_mp",
)


def roll_stat(base: int) -> int:
    """Один стат: base × (0.90 … 1.20), не ниже единицы.

    Результат зажимается в границы диапазона: на маленьких значениях
    (сила 5 у мага) округление иначе выносило бы стат за обещанные
    −10 %…+20 %.
    """
    if base <= 0:
        return base
    low = max(1, math.ceil(base * MIN_FACTOR))
    high = max(low, math.floor(base * MAX_FACTOR))
    value = int(round(base * random.uniform(MIN_FACTOR, MAX_FACTOR)))
    return max(low, min(high, value))


def roll_stats(base_stats: dict) -> dict:
    """Полный бросок стартовых характеристик по базе класса."""
    return {key: roll_stat(base_stats.get(key, 0)) for key in ROLLED_STATS}


def roll_quality(base_stats: dict, rolled: dict) -> int:
    """Насколько бросок удачен, в процентах от базы (90…120).

    Считается по сумме статов — так игрок видит одним числом, стоит ли
    перекатывать дальше.
    """
    base_total = sum(base_stats.get(k, 0) for k in ROLLED_STATS)
    if base_total <= 0:
        return 100
    rolled_total = sum(rolled.get(k, 0) for k in ROLLED_STATS)
    return int(round(rolled_total / base_total * 100))


def roll_verdict(quality: int) -> str:
    """Человеческая оценка броска — чтобы не считать проценты в уме."""
    if quality >= 115:
        return "🌟 Выдающийся бросок"
    if quality >= 108:
        return "✨ Отличный бросок"
    if quality >= 102:
        return "👍 Хороший бросок"
    if quality >= 97:
        return "😐 Средний бросок"
    return "💤 Слабый бросок"


def apply_stats(character, rolled: dict):
    """Записывает брошенные статы в персонажа и подтягивает HP/MP."""
    for key in ROLLED_STATS:
        if key in rolled:
            setattr(character, key, rolled[key])
    character.current_hp = character.max_hp
    character.current_mp = character.max_mp
    return character


def diff_line(base_stats: dict, rolled: dict, key: str) -> str:
    """Отклонение конкретного стата от базы: «+3» / «−1» / пусто."""
    base = base_stats.get(key, 0)
    value = rolled.get(key, base)
    delta = value - base
    if not delta:
        return ""
    return f" <i>({'+' if delta > 0 else '−'}{abs(delta)})</i>"
