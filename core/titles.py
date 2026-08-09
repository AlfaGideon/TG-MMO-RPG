"""Титулы, знаки доблести и достижения героя."""
import json
from core.models import Character

TITLES_CATALOG = {
    "Убийца Левиафана": {"icon": "🐙", "bonus_damage": 5, "desc": "+5 к урону"},
    "Первый Клинок Погоста": {"icon": "⚔️", "bonus_damage": 3, "desc": "+3 к урону"},
    "Несущий Свет": {"icon": "✨", "bonus_hp": 20, "desc": "+20 к здоровью"},
    "Осквернитель Могил": {"icon": "💀", "bonus_luck": 5, "desc": "+5 к удаче"},
    "Гладиатор Колизея": {"icon": "🩸", "bonus_defense": 5, "desc": "+5 к броне"},
    "Мастер Кузницы": {"icon": "🔨", "bonus_damage": 4, "desc": "+4 к урону"},
}


def get_unlocked_titles(character: Character) -> list[str]:
    raw = getattr(character, "unlocked_titles_json", "") or ""
    try:
        return list(json.loads(raw)) if raw else []
    except (ValueError, TypeError):
        return []


def unlock_title(character: Character, title_name: str) -> bool:
    if title_name not in TITLES_CATALOG:
        return False
    unlocked = get_unlocked_titles(character)
    if title_name not in unlocked:
        unlocked.append(title_name)
        character.unlocked_titles_json = json.dumps(unlocked, ensure_ascii=False)
        return True
    return False


def set_active_title(character: Character, title_name: str | None) -> bool:
    if title_name is None or title_name == "none":
        character.active_title = None
        return True
    unlocked = get_unlocked_titles(character)
    if title_name in unlocked:
        character.active_title = title_name
        return True
    return False


def title_bonus(character: Character) -> dict:
    active = getattr(character, "active_title", None)
    if not active or active not in TITLES_CATALOG:
        return {"damage": 0, "defense": 0, "hp": 0, "luck": 0}
    t = TITLES_CATALOG[active]
    return {
        "damage": t.get("bonus_damage", 0),
        "defense": t.get("bonus_defense", 0),
        "hp": t.get("bonus_hp", 0),
        "luck": t.get("bonus_luck", 0),
    }
