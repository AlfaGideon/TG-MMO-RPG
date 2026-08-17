"""Шаблоны питомцев: каталог, редактируемый из панели (IDEAS-100.md № 20).

Разделение, которое здесь важно не перепутать:

* `engine/familiars.py` — **механика**: три фиксированных спутника с
  боевыми бонусами, их герой заводит в боте;
* этот модуль — **редактируемый каталог** будущих видов, который админ
  наполняет сам. Именно он стоит за `PetTemplate` в серверной БД и за
  `store.settings["pet_templates"]` в браузерном стеке.

Пункт № 58 в своё время был снят как задача-фантом ровно потому, что
`core/pets.py` считали механикой; на деле это каталог. Поэтому здесь
нет боевых формул — только правила ключа, редкости и бонусов, общие для
обеих панелей. Валидация одна на два стека: раньше нормализация ключа и
разбор JSON-бонусов жили только в `core/pets.py`, и браузерная панель
не смогла бы принять шаблон по тем же правилам.
"""
import json
import re

TEMPLATES_KEY = "pet_templates"     # ключ в store.settings браузерного стека

RARITIES = ("common", "uncommon", "rare", "epic", "legendary")
RARITY_LABELS = {
    "common": "Обычный", "uncommon": "Необычный", "rare": "Редкий",
    "epic": "Эпический", "legendary": "Легендарный",
}
RARITY_ICONS = {
    "common": "⚪", "uncommon": "🟢", "rare": "🔵",
    "epic": "🟣", "legendary": "🟠",
}

FAMILIES = ("slime", "beast", "bird", "spirit", "construct")
FAMILY_LABELS = {
    "slime": "Слизни", "beast": "Звери", "bird": "Птицы",
    "spirit": "Духи", "construct": "Конструкты",
}

# Ключи бонусов, которые механика умеет читать (engine/familiars).
# Всё остальное в JSON допустимо, но помечается как «пока декоративный».
KNOWN_BONUSES = ("crit_bonus", "magic_bonus", "gold_to_stash_pct",
                 "vision_bonus", "berserk_bonus", "ambush_shield")


def normalize_key(value: str, fallback: str = "pet") -> str:
    """Стабильный ключ для колбэков и сохранений."""
    text = (value or "").strip().lower().replace(" ", "_")
    text = re.sub(r"[^a-z0-9а-яё_\-]+", "", text, flags=re.I)
    return text[:64] or fallback


def normalize_bonuses(value) -> str:
    """В хранилище всегда JSON-объект; мусор отклоняется явно."""
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    raw = (value or "").strip() or "{}"
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Бонусы должны быть JSON-объектом")
    return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))


def parse_bonuses(raw) -> dict:
    """Прочитать бонусы, не роняя экран на битой строке."""
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw or "{}")
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def normalize_rarity(value: str) -> str:
    value = (value or "").strip().lower()
    return value if value in RARITIES else "common"


def normalize_family(value: str) -> str:
    value = (value or "").strip().lower()
    return value if value in FAMILIES else "slime"


def make_template(name: str, key: str = "", description: str = "",
                  family: str = "slime", rarity: str = "common",
                  bonuses="{}", image_url: str = "",
                  sort_order: int = 100, is_active: bool = True) -> dict:
    """Собрать корректный шаблон. Бросает ValueError на пустом имени."""
    name = (name or "").strip()
    if not name:
        raise ValueError("У питомца должно быть имя")
    return {
        "key": normalize_key(key or name),
        "name": name[:128],
        "description": (description or "").strip()[:500],
        "family": normalize_family(family),
        "rarity": normalize_rarity(rarity),
        "bonuses_json": normalize_bonuses(bonuses),
        "image_url": (image_url or "").strip()[:512],
        "sort_order": int(sort_order or 100),
        "is_active": bool(is_active),
    }


def templates(store) -> list:
    """Шаблоны браузерного стека. Битые записи отбрасываются."""
    raw = store.settings.get(TEMPLATES_KEY)
    if not isinstance(raw, list):
        raw = []
        store.settings[TEMPLATES_KEY] = raw
    out = []
    for row in raw:
        if isinstance(row, dict) and row.get("name"):
            out.append(row)
    return sorted(out, key=lambda r: (int(r.get("sort_order", 100)),
                                      r.get("name", "")))


def add(store, **kwargs) -> dict:
    """Добавить шаблон. Ключ уникален: повтор перезаписывает запись."""
    tpl = make_template(**kwargs)
    rows = [r for r in templates(store) if r.get("key") != tpl["key"]]
    rows.append(tpl)
    store.settings[TEMPLATES_KEY] = rows
    return tpl


def remove(store, key: str) -> bool:
    """Удалить шаблон по ключу."""
    rows = templates(store)
    left = [r for r in rows if r.get("key") != key]
    store.settings[TEMPLATES_KEY] = left
    return len(left) != len(rows)


def toggle(store, key: str) -> bool | None:
    """Включить/выключить шаблон. Возвращает новое состояние или None."""
    rows = templates(store)
    for row in rows:
        if row.get("key") == key:
            row["is_active"] = not row.get("is_active", True)
            store.settings[TEMPLATES_KEY] = rows
            return row["is_active"]
    return None


def describe_bonuses(raw) -> str:
    """Человеческая строка бонусов для карточки шаблона."""
    data = parse_bonuses(raw)
    if not data:
        return "без бонусов"
    parts = []
    for key, val in data.items():
        mark = "" if key in KNOWN_BONUSES else " (пока декоративный)"
        parts.append(f"{key}: {val}{mark}")
    return " · ".join(parts)
