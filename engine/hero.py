"""Создание героя: перекат стартовых статов и дар к магии.

Герой больше не рождается с одинаковым для всех набором: статы катаются
от базы класса в диапазоне −10 %…+20 %. При создании даётся 10 попыток
переката — можно жать «ещё раз», пока не устроит бросок.

Отдельно бросается магическая предрасположенность: у кого-то её нет
вовсе, кто-то получил искру одной школы, редкие счастливчики — две.
"""
import math
import random

from engine import data

MIN_FACTOR = 0.90           # −10 %
MAX_FACTOR = 1.20           # +20 %
DEFAULT_REROLLS = 10

ROLLED = ("strength", "agility", "intelligence", "endurance", "luck",
          "max_hp", "max_mp")

# Вероятность каждой ступени дара, когда он вообще выпал
GRADE_WEIGHTS = [("weak", 40), ("normal", 38), ("strong", 17), ("gifted", 5)]

# Любимая школа класса выпадает заметно чаще прочих
PREFERRED_WEIGHT = 4


# ── статы ───────────────────────────────────────────────────

def base_stats(cls):
    """Базовый набор класса."""
    entry = data.CLASSES.get(cls)
    return dict(entry[2]) if entry else {}


def roll_stat(base):
    """Один стат: base × (0.90 … 1.20), зажатый в границы диапазона."""
    base = int(base)
    if base <= 0:
        return base
    low = max(1, math.ceil(base * MIN_FACTOR))
    high = max(low, math.floor(base * MAX_FACTOR))
    value = int(round(base * random.uniform(MIN_FACTOR, MAX_FACTOR)))
    return max(low, min(high, value))


def roll_stats(cls):
    """Полный бросок стартовых характеристик по базе класса."""
    base = base_stats(cls)
    return {key: roll_stat(base.get(key, 0)) for key in ROLLED}


def quality(cls, rolled):
    """Насколько бросок удачен, в процентах от базы (90…120)."""
    base = base_stats(cls)
    total = sum(base.get(k, 0) for k in ROLLED)
    if total <= 0:
        return 100
    return int(round(sum(rolled.get(k, 0) for k in ROLLED) / total * 100))


def verdict(q):
    """Человеческая оценка броска — чтобы не считать проценты в уме."""
    if q >= 115:
        return "🌟 Выдающийся бросок"
    if q >= 108:
        return "✨ Отличный бросок"
    if q >= 102:
        return "👍 Хороший бросок"
    if q >= 97:
        return "😐 Средний бросок"
    return "💤 Слабый бросок"


def diff(cls, rolled, key):
    """Отклонение стата от базы: « (+3)» / « (−1)» / пусто."""
    base = base_stats(cls).get(key, 0)
    delta = rolled.get(key, base) - base
    if not delta:
        return ""
    return f" <i>({'+' if delta > 0 else '−'}{abs(delta)})</i>"


def apply(p, cls, rolled, affinities):
    """Записывает бросок в игрока и фиксирует героя."""
    for key in ROLLED:
        if key in rolled:
            setattr(p, key, int(rolled[key]))
    p.cls = cls
    p.magic = list(affinities or [])
    p.hp, p.mp = p.max_hp, p.max_mp
    p.loc, p.x, p.y = 0, 5, 5
    p.rolls = 0
    p.roll_state = {}
    return p


# ── магия ───────────────────────────────────────────────────

def _grade():
    keys = [g for g, _ in GRADE_WEIGHTS]
    weights = [w for _, w in GRADE_WEIGHTS]
    return random.choices(keys, weights=weights, k=1)[0]


def roll_magic(cls):
    """Бросает дар. Возвращает [(школа, ступень)] — может быть пусто."""
    chance, dual, preferred = data.CLASS_MAGIC.get(cls, (0.5, 0.12, []))
    if random.random() > chance:
        return []
    schools = list(data.MAGIC_SCHOOLS)
    weights = [PREFERRED_WEIGHT if s in preferred else 1 for s in schools]
    first = random.choices(schools, weights=weights, k=1)[0]
    out = [(first, _grade())]
    if random.random() < dual:
        rest = [s for s in schools if s != first]
        rw = [PREFERRED_WEIGHT if s in preferred else 1 for s in rest]
        out.append((random.choices(rest, weights=rw, k=1)[0], _grade()))
    return out


def magic_lines(affinities):
    """Дар героя строками для профиля."""
    out = []
    for school, grade in affinities or []:
        icon, name, _desc = data.MAGIC_SCHOOLS.get(school, ("❔", school, ""))
        title, mult, mark = data.AFFINITY_GRADES.get(grade, ("Дар", 1.0, "•"))
        out.append(f"{icon} {name} {mark} <b>{title}</b> ×{mult}")
    return out


def magic_short(affinities):
    """Дар одной строкой: 🔥✦ ❄️•"""
    parts = []
    for school, grade in affinities or []:
        icon = data.MAGIC_SCHOOLS.get(school, ("❔",))[0]
        mark = data.AFFINITY_GRADES.get(grade, ("", 1.0, "•"))[2]
        parts.append(f"{icon}{mark}")
    return " ".join(parts) or "—"


def magic_power(p, school=""):
    """Множитель силы магии героя (по лучшей подходящей школе)."""
    best = 1.0
    for s, grade in getattr(p, "magic", None) or []:
        if school and s != school:
            continue
        mult = data.AFFINITY_GRADES.get(grade, ("", 1.0, ""))[1]
        best = max(best, mult)
    return best


# ── прокачка ────────────────────────────────────────────────

def growth(cls):
    """Прирост статов за уровень для класса."""
    return dict(data.CLASS_GROWTH.get(cls, {
        "strength": 1, "agility": 1, "intelligence": 1, "endurance": 1,
        "luck": 0, "max_hp": 10, "max_mp": 5,
    }))
