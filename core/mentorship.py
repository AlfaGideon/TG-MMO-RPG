"""Система наставничества: помощь новичкам и Очки Чести для ветеранов."""
from sqlalchemy import select
from core.models import Character


async def bind_mentor(session, apprentice: Character, mentor: Character) -> dict:
    """Взять новичка в ученики."""
    if mentor.id == apprentice.id:
        return {"ok": False, "reason": "Нельзя стать наставником самому себе."}
    if (mentor.level or 1) < 8:
        return {"ok": False, "reason": "Стать наставником может лишь опытный воин (8+ уровень)."}
    if (apprentice.level or 1) > 5:
        return {"ok": False, "reason": "Учеником может стать только начинающий путник (1–5 уровень)."}
    if apprentice.mentor_character_id:
        return {"ok": False, "reason": "У этого героя уже есть наставник."}

    apprentice.mentor_character_id = mentor.id
    await session.flush()
    return {
        "ok": True,
        "mentor_name": mentor.name,
        "apprentice_name": apprentice.name,
    }


async def reward_mentor_for_progress(session, apprentice: Character, points: int = 25) -> int:
    """Начисляет Очки Чести наставнику за успехи ученика."""
    if not apprentice.mentor_character_id:
        return 0
    mentor = await session.get(Character, apprentice.mentor_character_id)
    if not mentor:
        return 0
    mentor.honor_points = (mentor.honor_points or 0) + points
    await session.flush()
    return points


def get_mentorship_bonuses(character: Character) -> dict:
    """Бонусы ученика и наставника."""
    has_mentor = bool(character.mentor_character_id)
    return {
        "has_mentor": has_mentor,
        "exp_bonus_pct": 25 if has_mentor else 0,
        "honor_points": character.honor_points or 0,
    }
