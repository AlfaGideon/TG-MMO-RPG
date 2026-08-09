"""Руны, гнёзда экипировки и составные рунические слова (Runewords)."""
from core.models import ItemInstance

RUNES = {
    "rune_fire": {
        "name": "Руна Огня",
        "icon": "🔥",
        "bonus_damage": 10,
        "bonus_hp": 0,
        "desc": "+10 к урону огнём",
    },
    "rune_iron": {
        "name": "Руна Стали",
        "icon": "🛡",
        "bonus_damage": 0,
        "bonus_defense": 15,
        "desc": "+15 к броне и защите",
    },
    "rune_void": {
        "name": "Руна Бездны",
        "icon": "🌑",
        "bonus_damage": 12,
        "bonus_luck": 5,
        "desc": "+12 урона тьмой и +5 к удаче",
    },
    "rune_light": {
        "name": "Руна Света",
        "icon": "✨",
        "bonus_hp": 30,
        "bonus_damage": 8,
        "desc": "+30 HP и +8 святого урона",
    },
}

RUNEWORDS = {
    frozenset(["rune_fire", "rune_iron"]): {
        "name": "Пламенная сталь",
        "bonus_damage": 20,
        "bonus_defense": 15,
        "desc": "Сверхпрочный сплав: +20 к урону и +15 к защите!",
    },
    frozenset(["rune_void", "rune_void"]): {
        "name": "Взор Бездны",
        "bonus_damage": 25,
        "bonus_luck": 12,
        "desc": "Взор из глубин: +25 к урону тьмы и +12 к удаче!",
    },
    frozenset(["rune_light", "rune_iron"]): {
        "name": "Благословение Рассвета",
        "bonus_hp": 60,
        "bonus_defense": 20,
        "desc": "Священные латы: +60 к макс. здоровью и +20 к защите!",
    },
    frozenset(["rune_fire", "rune_void"]): {
        "name": "Пепельное пламя",
        "bonus_damage": 30,
        "bonus_hp": 15,
        "desc": "Раскалённый пепел: +30 к урону и +15 HP!",
    },
}


def check_runeword(r1: str | None, r2: str | None) -> dict | None:
    if not r1 or not r2:
        return None
    pair = frozenset([r1, r2])
    return RUNEWORDS.get(pair)


def insert_rune(instance: ItemInstance, rune_key: str, slot: int = 1) -> dict:
    """Вставить руну в свободное гнездо предмета."""
    if rune_key not in RUNES:
        return {"ok": False, "reason": "Неизвестная руна."}

    if slot == 1:
        instance.socket_1 = rune_key
    elif slot == 2:
        instance.socket_2 = rune_key
    else:
        return {"ok": False, "reason": "Неверный слот руны."}

    # Применяем базовые бонусы руны
    rdata = RUNES[rune_key]
    instance.bonus_damage = (instance.bonus_damage or 0) + rdata.get("bonus_damage", 0)
    instance.bonus_defense = (instance.bonus_defense or 0) + rdata.get("bonus_defense", 0)
    instance.bonus_hp = (instance.bonus_hp or 0) + rdata.get("bonus_hp", 0)
    instance.bonus_luck = (instance.bonus_luck or 0) + rdata.get("bonus_luck", 0)

    # Проверяем составление рунического слова
    s1 = getattr(instance, "socket_1", None)
    s2 = getattr(instance, "socket_2", None)
    rw = check_runeword(s1, s2)
    formed_runeword = None
    if rw:
        instance.runeword = rw["name"]
        instance.bonus_damage = (instance.bonus_damage or 0) + rw.get("bonus_damage", 0)
        instance.bonus_defense = (instance.bonus_defense or 0) + rw.get("bonus_defense", 0)
        instance.bonus_hp = (instance.bonus_hp or 0) + rw.get("bonus_hp", 0)
        formed_runeword = rw["name"]

    return {
        "ok": True,
        "rune": rdata["name"],
        "runeword": formed_runeword,
        "instance": instance,
    }
