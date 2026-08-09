"""Круги перерождения (Rebirth & Prestige) для эндгейм-ветеранов."""
from core.models import Character

REBIRTH_MIN_LEVEL = 15


def can_rebirth(character: Character) -> tuple[bool, str]:
    if (character.level or 1) < REBIRTH_MIN_LEVEL:
        return False, f"Перерождение доступно лишь героям, достигшим {REBIRTH_MIN_LEVEL}-го уровня!"
    return True, "Герой готов совершить ритуал Вечного Перерождения!"


async def perform_rebirth(session, character: Character) -> dict:
    """Сброс уровня до 1-го с получением постоянного бонуса «Искра Бессмертия»."""
    ok, reason = can_rebirth(character)
    if not ok:
        return {"ok": False, "reason": reason}

    character.rebirth_count = (character.rebirth_count or 0) + 1
    character.level = 1
    character.experience = 0

    # Искра Бессмертия: увеличивает базовые статы на +10% за каждый круг перерождения
    character.strength = max(10, int((character.strength or 10) * 1.10))
    character.agility = max(10, int((character.agility or 10) * 1.10))
    character.intelligence = max(10, int((character.intelligence or 10) * 1.10))
    character.endurance = max(10, int((character.endurance or 10) * 1.10))
    character.luck = max(10, int((character.luck or 10) * 1.10))
    character.max_hp = max(100, int((character.max_hp or 100) * 1.10))
    character.current_hp = character.max_hp

    await session.flush()
    return {
        "ok": True,
        "rebirth_count": character.rebirth_count,
        "title": "🔥 ВЕЧНОЕ ПЕРЕРОЖДЕНИЕ СОВЕРШЕНО!",
        "desc": f"Твоя душа очистилась в пламени! Получен {character.rebirth_count}-й ранг «Искры Бессмертия» (+10% ко всем статам навсегда)!",
    }
