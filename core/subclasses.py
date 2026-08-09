"""Специализации и подклассы героев (Ascendancy Subclasses)."""
from core.models import Character

SUBCLASSES = {
    "berserker": {
        "name": "🪓 Берсерк",
        "class_base": "warrior",
        "desc": "Ярость битвы: урон увеличивается пропорционально потерянному здоровью, иммунитет к оглушению.",
        "damage_mult": 1.25,
        "vampirism_pct": 10,
        "crit_bonus": 5.0,
    },
    "paladin": {
        "name": "🛡 Паладин",
        "class_base": "warrior",
        "desc": "Святой защитник: +30% к броне, святой урон +20 и аура исцеления.",
        "defense_mult": 1.30,
        "holy_damage": 20,
        "hp_bonus": 50,
    },
    "archmage": {
        "name": "⚡ Архимаг стихий",
        "class_base": "mage",
        "desc": "Повелитель первородных сил: +50% к урону всех стихийных комбо-реакций, −20% расход маны.",
        "magic_mult": 1.35,
        "mana_bonus": 50,
    },
    "necromancer": {
        "name": "💀 Некромант",
        "class_base": "mage",
        "desc": "Владыка праха: 20% вампиризм от всех атак, усиление магии Тьмы на +30%.",
        "vampirism_pct": 20,
        "dark_mult": 1.30,
    },
    "assassin": {
        "name": "🗡 Ассасин",
        "class_base": "rogue",
        "desc": "Смертоносная тень: +20% шанс крита и +100% критический урон из засады.",
        "crit_bonus": 20.0,
        "crit_damage_mult": 1.50,
    },
    "tracker": {
        "name": "🏹 Следопыт",
        "class_base": "ranger",
        "desc": "Хозяин пустошей: обход любых ловушек в подземельях и +25% к опыту охоты.",
        "trap_immunity": True,
        "exp_bonus_pct": 25,
    },
}


def get_available_subclasses(character_class: str) -> list[dict]:
    """Возвращает доступные подклассы для базового класса героя."""
    c_lower = str(character_class).lower()
    res = []
    for key, data in SUBCLASSES.items():
        if data["class_base"] == c_lower or c_lower in ("ranger", "rogue") and data["class_base"] in ("ranger", "rogue"):
            item = data.copy()
            item["key"] = key
            res.append(item)
    return res or [SUBCLASSES["berserker"], SUBCLASSES["paladin"]]


def choose_subclass(character: Character, subclass_key: str) -> dict:
    """Выбор специализации подкласса."""
    if (character.level or 1) < 10:
        return {"ok": False, "reason": "Специализация доступна только с 10-го уровня!"}
    if subclass_key not in SUBCLASSES:
        return {"ok": False, "reason": "Неизвестный подкласс."}

    character.subclass = subclass_key
    sub = SUBCLASSES[subclass_key]
    return {
        "ok": True,
        "subclass_name": sub["name"],
        "desc": sub["desc"],
    }


def subclass_bonuses(character: Character) -> dict:
    sub_key = getattr(character, "subclass", None)
    if not sub_key or sub_key not in SUBCLASSES:
        return {"damage_mult": 1.0, "defense_mult": 1.0, "vampirism_pct": 0, "crit_bonus": 0.0}
    data = SUBCLASSES[sub_key]
    return {
        "damage_mult": data.get("damage_mult", 1.0),
        "defense_mult": data.get("defense_mult", 1.0),
        "vampirism_pct": data.get("vampirism_pct", 0),
        "crit_bonus": data.get("crit_bonus", 0.0),
        "name": data["name"],
    }
