"""Очки характеристик: герой сам распределяет прирост с уровней.

Раньше класс фиксировано «докармливал» статы при каждом уровне, и игрок
никак не влиял на развитие героя. Теперь уровень даёт очки характеристик
(чем круглее уровень — тем больше), а вложить их можно в любой параметр
в профиле — инлайн-кнопками плюс/минус. Вложенные очки можно в любой
момент снять и переложить; базовые (стартовые) статы неизменны.

Каждое вложенное очко — это +1 к выбранному стату; Выносливость и
Интеллект дополнительно поднимают запас HP и MP соответственно.
"""
import json

ALLOCATABLE = ("strength", "agility", "intelligence", "endurance", "luck")

STAT_LABELS = {
    "strength": ("💪", "Сила"),
    "agility": ("🏃", "Ловкость"),
    "intelligence": ("🧠", "Интеллект"),
    "endurance": ("🛡", "Выносливость"),
    "luck": ("🍀", "Удача"),
}

# Бонусы сверх «+1 к стату» за одно вложенное очко.
HP_PER_ENDURANCE = 10
MP_PER_INTELLIGENCE = 5

STAT_EFFECTS = {
    "strength": "+1 к урону в ближней битве",
    "agility": "+1 к ловкости: точность, побег, инициатива",
    "intelligence": f"+1 к колдовской мощи, +{MP_PER_INTELLIGENCE} 💙 макс. MP",
    "endurance": f"+1 к стойкости, +{HP_PER_ENDURANCE} ❤️ макс. HP",
    "luck": "+1 к удаче: криты и редкие находки",
}


def perks_for_level(level: int) -> int:
    """Сколько очков даёт достижение `level`-го уровня.

    Количество разное: обычный уровень — 3 очка, каждый пятый — щедрее,
    каждый десятый — ещё щедрее (бонусы суммируются).
    """
    points = 3
    if level % 5 == 0:
        points += 2
    if level % 10 == 0:
        points += 3
    return points


def load_allocated(character) -> dict:
    """Сколько очков игрок уже вложил в каждый стат (не считая базы)."""
    raw = getattr(character, "allocated_stats", "") or ""
    try:
        data = json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        data = {}
    return {key: int(data.get(key, 0)) for key in ALLOCATABLE}


def save_allocated(character, data: dict) -> None:
    character.allocated_stats = json.dumps(
        {k: int(v) for k, v in data.items() if k in ALLOCATABLE and v},
        ensure_ascii=False)


def free_points(character) -> int:
    return max(0, int(getattr(character, "stat_points", 0) or 0))


def allocate(character, key: str) -> bool:
    """Вложить одно свободное очко. False — очков нет или ключ чужой."""
    if key not in ALLOCATABLE or free_points(character) <= 0:
        return False
    character.stat_points = free_points(character) - 1
    data = load_allocated(character)
    data[key] = data.get(key, 0) + 1
    save_allocated(character, data)
    _apply(character, key, +1)
    return True


def deallocate(character, key: str) -> bool:
    """Снять вложенное очко обратно в резерв. Базу снять нельзя."""
    if key not in ALLOCATABLE:
        return False
    data = load_allocated(character)
    if data.get(key, 0) <= 0:
        return False
    data[key] -= 1
    save_allocated(character, data)
    character.stat_points = free_points(character) + 1
    _apply(character, key, -1)
    return True


def effect_preview(character, key: str) -> str:
    """Одной строкой — что даст следующее очко в этот стат."""
    emoji, label = STAT_LABELS[key]
    return f"{emoji} {label}: {STAT_EFFECTS[key]}"


def _apply(character, key: str, sign: int) -> None:
    """Проводит +1/−1 стата и побочный бонус HP/MP (к зачислению и снятию)."""
    current = int(getattr(character, key, 0) or 0)
    setattr(character, key, max(1, current + sign))  # стат не бывает < 1
    if key == "endurance":
        character.max_hp = max(
            1, (character.max_hp or 0) + sign * HP_PER_ENDURANCE)
        if sign > 0:
            character.current_hp = (character.current_hp or 0) + HP_PER_ENDURANCE
        else:
            character.current_hp = min(character.current_hp or 1, character.max_hp)
    elif key == "intelligence":
        character.max_mp = max(
            0, (character.max_mp or 0) + sign * MP_PER_INTELLIGENCE)
        if sign > 0:
            character.current_mp = (character.current_mp or 0) + MP_PER_INTELLIGENCE
        else:
            character.current_mp = min(character.current_mp or 0, character.max_mp)
