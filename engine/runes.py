"""Руны, гнёзда экипировки и рунические слова.

Каталоги рун и слов — **единственный источник правды** для обоих стеков:
`core/runes.py` реэкспортирует их отсюда. Вставка руны работает с любым
объектом, у которого есть поля `socket_1/socket_2` и `bonus_*`: и с
серверным `ItemInstance`, и с записью реестра `engine/items.py`
(для неё есть обёртка `insert_into_instance` ниже).
"""

SOCKETS = 2      # сколько гнёзд у предмета: больше — уже не «слово», а салат

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


def insert_rune(instance, rune_key: str, slot: int = 1) -> dict:
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


def rune_icon(key: str) -> str:
    return RUNES.get(key, {}).get("icon", "◻️")


def socket_line(instance) -> str:
    """Строка гнёзд для карточки предмета: «🔥 Руна Огня · пусто»."""
    parts = []
    for slot in range(1, SOCKETS + 1):
        key = getattr(instance, f"socket_{slot}", None)
        if key and key in RUNES:
            parts.append(f"{RUNES[key]['icon']} {RUNES[key]['name']}")
        else:
            parts.append("◻️ пусто")
    word = getattr(instance, "runeword", None)
    tail = f" · <b>{word}</b>" if word else ""
    return " · ".join(parts) + tail


class _DictInstance:
    """Обёртка над записью реестра `engine/items.py` под API insert_rune.

    Экземпляры браузерного стека — обычные словари, а `insert_rune`
    ожидает объект с атрибутами. Обёртка пишет изменения обратно в dict,
    чтобы не заводить вторую копию логики рун.
    """

    _FIELDS = ("socket_1", "socket_2", "runeword",
               "bonus_damage", "bonus_defense", "bonus_hp", "bonus_luck")

    def __init__(self, data: dict):
        object.__setattr__(self, "_data", data)

    def __getattr__(self, name):
        if name in self._FIELDS:
            if name.startswith("bonus_"):
                stats = self._data.get("stats") or {}
                return stats.get(name.replace("bonus_", ""), 0)
            return self._data.get(name)
        raise AttributeError(name)

    def __setattr__(self, name, value):
        if name in self._FIELDS:
            if name.startswith("bonus_"):
                stats = self._data.setdefault("stats", {})
                stats[name.replace("bonus_", "")] = value
            else:
                self._data[name] = value
            return
        object.__setattr__(self, name, value)


def insert_into_instance(inst: dict, rune_key: str, slot: int = 1) -> dict:
    """Вставить руну в экземпляр браузерного стека (запись реестра)."""
    if not isinstance(inst, dict):
        return insert_rune(inst, rune_key, slot)
    wrapper = _DictInstance(inst)
    res = insert_rune(wrapper, rune_key, slot)
    if res.get("ok"):
        res["instance"] = inst
    return res
