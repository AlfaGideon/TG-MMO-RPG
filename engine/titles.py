"""Титулы: знаки доблести и их бонусы.

Каталог живёт здесь — это **единственный источник правды** для обоих
стеков: `core/titles.py` реэкспортирует `TITLES_CATALOG` отсюда (тот же
приём, что у знамений). Так герой с титулом «Убийца Левиафана» получает
одинаковую прибавку и в браузере, и в боте.

Функции работают с любым объектом, у которого есть поля
`unlocked_titles_json` и `active_title` — это и `engine.models.Player`,
и серверный `core.models.Character`, поэтому логика не дублируется.
"""
import json

TITLES_CATALOG = {
    "Убийца Левиафана": {"icon": "🐙", "bonus_damage": 5, "desc": "+5 к урону"},
    "Первый Клинок Погоста": {"icon": "⚔️", "bonus_damage": 3, "desc": "+3 к урону"},
    "Несущий Свет": {"icon": "✨", "bonus_hp": 20, "desc": "+20 к здоровью"},
    "Осквернитель Могил": {"icon": "💀", "bonus_luck": 5, "desc": "+5 к удаче"},
    "Гладиатор Колизея": {"icon": "🩸", "bonus_defense": 5, "desc": "+5 к броне"},
    "Мастер Кузницы": {"icon": "🔨", "bonus_damage": 4, "desc": "+4 к урону"},
}


def get_unlocked_titles(character) -> list:
    raw = getattr(character, "unlocked_titles_json", "") or ""
    try:
        return list(json.loads(raw)) if raw else []
    except (ValueError, TypeError):
        # Битое поле в сохранении не должно ронять профиль героя.
        return []


def unlock_title(character, title_name: str) -> bool:
    """Открыть титул. False — такого титула нет или он уже открыт."""
    if title_name not in TITLES_CATALOG:
        return False
    unlocked = get_unlocked_titles(character)
    if title_name in unlocked:
        return False
    unlocked.append(title_name)
    character.unlocked_titles_json = json.dumps(unlocked, ensure_ascii=False)
    return True


def set_active_title(character, title_name) -> bool:
    """Надеть титул. Носить можно только открытый."""
    if title_name is None or title_name == "none":
        character.active_title = None
        return True
    if title_name in get_unlocked_titles(character):
        character.active_title = title_name
        return True
    return False


def title_bonus(character) -> dict:
    """Прибавки активного титула (нули, если титул не надет)."""
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


def title_line(character) -> str:
    """Строка активного титула для профиля ('' — титула нет)."""
    active = getattr(character, "active_title", None)
    if not active or active not in TITLES_CATALOG:
        return ""
    t = TITLES_CATALOG[active]
    return f"{t['icon']} <b>{active}</b> · <i>{t['desc']}</i>"
