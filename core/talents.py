"""Звёздное древо пассивных созвездий (Passive Constellations)."""
import json
from core.models import Character

TALENT_STARS = {
    "star_fortitude": {
        "name": "⭐ Звезда Стойкости",
        "desc": "+50 к максимальному здоровью и +10 к броне",
        "hp_bonus": 50,
        "defense_bonus": 10,
    },
    "star_wrath": {
        "name": "⭐ Звезда Ярости",
        "desc": "+15 к базовому урону и +5% к шансу крита",
        "damage_bonus": 15,
        "crit_bonus": 5.0,
    },
    "star_magic": {
        "name": "⭐ Звезда Магии",
        "desc": "+30 к запасу маны и +15 к магической мощи",
        "mp_bonus": 30,
        "magic_power": 15,
    },
    "star_fortune": {
        "name": "⭐ Звезда Удачи",
        "desc": "+10 к удаче и +10% шанс на редкий дроп",
        "luck_bonus": 10,
        "drop_bonus_pct": 10,
    },
    "star_pocket": {
        "name": "⭐ Звезда Бездонного Кармана",
        "desc": "+2 дополнительные ячейки защищённого кармана",
        "stash_bonus": 2,
    },
}


def get_unlocked_talents(character: Character) -> list[str]:
    raw = getattr(character, "talents_json", "") or ""
    try:
        return list(json.loads(raw)) if raw else []
    except (ValueError, TypeError):
        return []


def unlock_talent(character: Character, talent_key: str) -> dict:
    """Активировать звезду созвездия."""
    if talent_key not in TALENT_STARS:
        return {"ok": False, "reason": "Неизвестная звезда созвездия."}

    unlocked = get_unlocked_talents(character)
    if talent_key in unlocked:
        return {"ok": False, "reason": "Эта звезда уже зажжена!"}

    pts = getattr(character, "talent_points", 0) or 0
    if pts <= 0:
        return {"ok": False, "reason": "Нет свободных очков талантов (выдаются каждые 3 уровня)."}

    character.talent_points = pts - 1
    unlocked.append(talent_key)
    character.talents_json = json.dumps(unlocked, ensure_ascii=False)

    star = TALENT_STARS[talent_key]
    # Начисляем бонусы
    if "hp_bonus" in star:
        character.max_hp = (character.max_hp or 100) + star["hp_bonus"]
        character.current_hp = character.max_hp
    if "mp_bonus" in star:
        character.max_mp = (character.max_mp or 50) + star["mp_bonus"]
        character.current_mp = character.max_mp

    return {
        "ok": True,
        "star_name": star["name"],
        "desc": star["desc"],
    }


def talent_bonuses(character: Character) -> dict:
    unlocked = get_unlocked_talents(character)
    dmg = def_val = luck = stash = 0
    crit = 0.0
    for k in unlocked:
        star = TALENT_STARS.get(k, {})
        dmg += star.get("damage_bonus", 0)
        def_val += star.get("defense_bonus", 0)
        luck += star.get("luck_bonus", 0)
        stash += star.get("stash_bonus", 0)
        crit += star.get("crit_bonus", 0.0)
    return {
        "damage": dmg,
        "defense": def_val,
        "luck": luck,
        "stash": stash,
        "crit": crit,
    }
