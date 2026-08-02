"""Предрасположенность героя к школам магии.

Шесть школ: огонь, лёд, гроза, тьма, природа, свет. При создании героя
бросается дар: кому-то не досталось ничего, кто-то получил искру одной
школы, а редкие счастливчики — талант сразу к двум.

Дар не заменяет статы, а умножает эффект магических умений и бонусы от
предметов соответствующей школы.
"""
import random

from sqlalchemy import select

from core.enums import (
    AFFINITY_GRADES, MAGIC_SCHOOLS, AffinityGrade, MagicSchool,
)
from core.models import CharacterAffinity

SCHOOL_KEYS = [s.value for s in MagicSchool]

# Насколько вероятна каждая ступень дара, когда он вообще выпал
GRADE_WEIGHTS = [
    (AffinityGrade.WEAK.value, 40),
    (AffinityGrade.NORMAL.value, 38),
    (AffinityGrade.STRONG.value, 17),
    (AffinityGrade.GIFTED.value, 5),
]

# Школа, к которой класс склонен, выпадает заметно чаще прочих
PREFERRED_WEIGHT = 4


def school_icon(school: str) -> str:
    return MAGIC_SCHOOLS.get(str(school), ("❔", "", ""))[0]


def school_name(school: str) -> str:
    return MAGIC_SCHOOLS.get(str(school), ("", "Неизвестная школа", ""))[1]


def school_description(school: str) -> str:
    return MAGIC_SCHOOLS.get(str(school), ("", "", ""))[2]


def grade_title(grade: str) -> str:
    return AFFINITY_GRADES.get(str(grade), ("Дар", 1.0, "•"))[0]


def grade_multiplier(grade: str) -> float:
    return AFFINITY_GRADES.get(str(grade), ("Дар", 1.0, "•"))[1]


def grade_mark(grade: str) -> str:
    return AFFINITY_GRADES.get(str(grade), ("Дар", 1.0, "•"))[2]


def _roll_grade() -> str:
    keys = [g for g, _ in GRADE_WEIGHTS]
    weights = [w for _, w in GRADE_WEIGHTS]
    return random.choices(keys, weights=weights, k=1)[0]


def roll_affinities(cls_def=None) -> list[tuple[str, str]]:
    """Бросает дар к магии. Возвращает список пар (школа, ступень).

    Пустой список — герой родился без магического дара, и это нормально:
    воину он и не нужен.
    """
    chance = 0.5 if cls_def is None else (cls_def.affinity_chance if cls_def.affinity_chance is not None else 0.5)
    dual = 0.12 if cls_def is None else (cls_def.dual_affinity_chance if cls_def.dual_affinity_chance is not None else 0.12)

    if random.random() > chance:
        return []

    preferred = set(cls_def.preferred_school_list()) if cls_def is not None else set()
    weights = [
        PREFERRED_WEIGHT if key in preferred else 1
        for key in SCHOOL_KEYS
    ]

    first = random.choices(SCHOOL_KEYS, weights=weights, k=1)[0]
    out = [(first, _roll_grade())]

    if random.random() < dual:
        rest = [k for k in SCHOOL_KEYS if k != first]
        rest_weights = [
            PREFERRED_WEIGHT if k in preferred else 1 for k in rest
        ]
        second = random.choices(rest, weights=rest_weights, k=1)[0]
        out.append((second, _roll_grade()))

    return out


async def set_affinities(session, character, pairs: list[tuple[str, str]]):
    """Полностью заменяет набор даров персонажа."""
    result = await session.execute(
        select(CharacterAffinity).where(
            CharacterAffinity.character_id == character.id
        )
    )
    for row in result.scalars().all():
        session.delete(row)
    await session.flush()

    created = []
    for school, grade in pairs[:2]:
        if school not in SCHOOL_KEYS:
            continue
        row = CharacterAffinity(
            character_id=character.id, school=school, grade=grade,
        )
        session.add(row)
        created.append(row)
    await session.flush()
    return created


async def get_affinities(session, character_id: int):
    result = await session.execute(
        select(CharacterAffinity)
        .where(CharacterAffinity.character_id == character_id)
        .order_by(CharacterAffinity.id)
    )
    return result.scalars().all()


def affinity_power(affinities, school: str) -> float:
    """Множитель силы для конкретной школы: 0.0, если дара нет."""
    for row in affinities:
        if row.school == str(school):
            return grade_multiplier(row.grade)
    return 0.0


def best_affinity(affinities):
    """Самый сильный дар героя — им он и колдует по умолчанию."""
    if not affinities:
        return None
    return max(affinities, key=lambda a: grade_multiplier(a.grade))


def affinity_line(affinities) -> str:
    """Короткая строка для профиля: «🔥 Огонь ✦ Сильный дар»."""
    if not affinities:
        return "🚫 <i>Магического дара нет</i>"
    parts = []
    for row in affinities:
        parts.append(
            f"{school_icon(row.school)} {school_name(row.school)} "
            f"{grade_mark(row.grade)} <i>{grade_title(row.grade)}</i>"
        )
    return "\n".join(parts)


def spell_bonus(affinities, character_intelligence: int) -> int:
    """Прибавка к магическому урону от лучшего дара героя."""
    best = best_affinity(affinities)
    if best is None:
        return 0
    return int(round(character_intelligence * 0.35 * grade_multiplier(best.grade)))
