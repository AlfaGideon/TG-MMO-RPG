"""Питомцы и фамильяры: пассивные спутники с узкой специализацией.

Каталог общий для обоих стеков — `core/familiars.py` реэкспортирует его
отсюда, поэтому Ворон стоит одинаково и в браузере, и в боте.
Цены указаны в бронзе (см. `engine/currency`).
"""

FAMILIARS = {
    "crow": {
        "icon": "🦅",
        "name": "Ворон-падальщик",
        "desc": "Автоматически сохраняет 50% золота сразу в защищённый карман и даёт +5% к шансу крита.",
        "gold_to_stash_pct": 50,
        "crit_bonus": 5.0,
        "cost": 500,
    },
    "firefly": {
        "icon": "💡",
        "name": "Светляк Бездны",
        "desc": "Рассеивает туман войны дальше и усиливает заклинания стихий на +15%.",
        "magic_bonus": 15,
        "vision_bonus": 1,
        "cost": 500,
    },
    "hound": {
        "icon": "🐺",
        "name": "Теневой пёс",
        "desc": "Предупреждает о засадах охотников и даёт +15% к урону в стойке Берсерка.",
        "ambush_shield": True,
        "berserk_bonus": 15,
        "cost": 600,
    },
}


def get_familiar(character) -> dict | None:
    """Возвращает параметры текущего активного фамильяра или None."""
    ftype = getattr(character, "familiar_type", None)
    if not ftype or ftype not in FAMILIARS:
        return None
    data = FAMILIARS[ftype].copy()
    data["type"] = ftype
    data["level"] = getattr(character, "familiar_level", 1) or 1
    data["custom_name"] = getattr(character, "familiar_name", "") or data["name"]
    return data


def set_familiar(character, familiar_type: str, custom_name: str = "") -> bool:
    """Привязать фамильяра к герою."""
    if familiar_type not in FAMILIARS:
        return False
    character.familiar_type = familiar_type
    character.familiar_level = 1
    character.familiar_name = custom_name or FAMILIARS[familiar_type]["name"]
    return True


def familiar_bonuses(character) -> dict:
    """Пассивные бонусы от активного питомца."""
    fam = get_familiar(character)
    if not fam:
        return {"crit_bonus": 0.0, "magic_bonus": 0, "gold_to_stash_pct": 0, "berserk_bonus": 0}
    lvl = fam["level"]
    return {
        "crit_bonus": fam.get("crit_bonus", 0.0) + (lvl - 1) * 0.5,
        "magic_bonus": fam.get("magic_bonus", 0) + (lvl - 1) * 2,
        "gold_to_stash_pct": fam.get("gold_to_stash_pct", 0),
        "berserk_bonus": fam.get("berserk_bonus", 0) + (lvl - 1) * 2,
    }


def familiar_card_text(character) -> str:
    fam = get_familiar(character)
    if not fam:
        return (
            "🐾 <b>Фамильяры и спутники</b>\n\n"
            "У тебя пока нет верного спутника.\n\n"
            "<i>Фамильяры сопровождают героя в походах, помогают собирать добычу "
            "и дают постоянные пассивные усиления.</i>"
        )
    return (
        f"🐾 <b>Фамильяр: {fam['icon']} {fam['custom_name']}</b> (Ур. {fam['level']})\n\n"
        f"Вид: <b>{fam['name']}</b>\n"
        f"<i>{fam['desc']}</i>"
    )
