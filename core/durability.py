"""Серверная обёртка правил прочности снаряжения (2.2).

Браузерный движок хранит экземпляры как dict, серверный — как ORM
`ItemInstance`. Правила одни: `engine.durability` реэкспортируется, а здесь
только адаптация `getattr`/`get` и обход экипировки через `InventoryItem`.
"""

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from engine import durability as rules

GEAR_TYPES = rules.GEAR_TYPES
RULES = rules.RULES
rarity_mult = rules.rarity_mult


def _rare(inst) -> str:
    val = getattr(inst, "rarity", None)
    if hasattr(val, "value"):
        val = val.value
    return str(val or "common").lower()


def _type(inst, item=None) -> str:
    if item is not None:
        val = getattr(item, "item_type", None)
    else:
        val = getattr(inst, "item_type", None) or getattr(inst, "type", None)
    if hasattr(val, "value"):
        val = val.value
    return str(val or "").lower()


def is_gear(inst, item=None) -> bool:
    return bool(inst) and _type(inst, item) in GEAR_TYPES


def max_of(inst) -> int:
    return max(1, int(getattr(inst, "durability_max", None)
                      or RULES["max"]))


def cur(inst) -> int:
    raw = getattr(inst, "durability", None)
    if raw is None:
        raw = max_of(inst)
    return max(0, min(max_of(inst), int(raw or 0)))


def broken(inst) -> bool:
    return cur(inst) <= 0


def repair_cost(inst) -> int:
    missing = max(0, max_of(inst) - cur(inst))
    return max(1, int(round(missing * RULES["cost_per"] * rarity_mult(_rare(inst)))))


def repair_materials(inst) -> dict:
    return {int(RULES["material"]): 1}


def repair(inst) -> dict:
    """Починить ORM-экземпляр. Возвращает (было, стало, цена)."""
    was = cur(inst)
    cost = repair_cost(inst)
    if was >= max_of(inst):
        return {"ok": False, "was": was, "now": was, "cost": 0,
                "reason": "в исправности"}
    setattr(inst, "durability", max_of(inst))
    return {"ok": True, "was": was, "now": int(getattr(inst, "durability")),
            "cost": cost}


def card_line(inst, item=None) -> str:
    """Строка прочности для серверной карточки/списка."""
    if not is_gear(inst, item):
        return ""
    now, cap = cur(inst), max_of(inst)
    if broken(inst):
        return "🔩 <b>Прочность: 0/макс</b> — сломано, почини в кузнице!"
    icon = "🟩" if now >= cap * 0.7 else "🟨" if now >= cap * 0.3 else "🟥"
    return f"🔩 Прочность: {icon} {now}/{cap}"


async def decay(session, character, kind="attack"):
    """Снять прочность с надетого снаряжения сервера.

    `attack` — оружие; `taken` — защитные слоты; `death` — всё надетое.
    Возвращает строки-предупреждения о сломавшихся вещах.
    """
    if kind not in ("attack", "taken", "death"):
        return []
    result = await session.execute(
        select(InventoryItem)
        .options(selectinload(InventoryItem.instance).selectinload(ItemInstance.item),
                 selectinload(InventoryItem.item))
        .where(InventoryItem.character_id == character.id)
        .where(InventoryItem.is_equipped == True)  # noqa: E712
    )
    warnings = []
    targets = {"attack": {"weapon"},
               "taken": {"armor", "helmet", "boots", "accessory"},
               "death": {"weapon", "armor", "helmet", "boots", "accessory"}}[kind]
    amount = (RULES["attack_hit"] if kind == "attack"
              else RULES["taken_hit"] if kind == "taken"
              else RULES["death"])
    for row in result.scalars().all():
        inst = row.instance
        item = row.item
        if inst is None or not is_gear(inst, item):
            continue
        if _type(inst, item).lower() not in targets:
            continue
        was = cur(inst)
        setattr(inst, "durability", max(0, was - amount))
        if was > 0 and cur(inst) <= 0:
            name = (item.name if item is not None
                    else getattr(inst, "display_name", lambda: "вещь")())
            warnings.append(f"🔩 <b>{name}</b> заклинило! Почини в кузнице.")
    await session.flush()
    return warnings


# Материал ремонта: движок хранит индекс, сервер — имя шаблона в БД.
REPAIR_MATERIAL_NAME = "Ржавый лом"


async def find_repair_material(session) -> "Item | None":
    """Найти предмет-материал для ремонта по имени (иначе None)."""
    result = await session.execute(
        select(Item).where(Item.name == REPAIR_MATERIAL_NAME)
    )
    return result.scalar_one_or_none()


# Импорт внизу, чтобы не тянуть модели до объявления движка-правил.
from core.models import Item, InventoryItem, ItemInstance  # noqa: E402
