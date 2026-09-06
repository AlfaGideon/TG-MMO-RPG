"""🔩 Прочность снаряжения: износ и ремонт.

Идея 2.2 из IDEAS-new-2026.md. Правила — единственный источник правды
для обоих стеков: `core/durability.py` реэкспортирует их, поэтому бот и
браузерный движок не разъедутся.

Первая итерация намеренно маленькая:
  * прочность есть у 5 типов экипировки (оружие/броня/шлем/обувь/аксессуар);
  * в бою оружие стачивается об удар, остальные слоты — когда бьют героя;
  * смерть дополнительно треплет всё надетое;
  * при 0 вещь «заклинило» — статы не работают, надеть нельзя;
  * чинится за бронзу + железный лом у кузницы.

Расходники и материалы не изнашиваются: они не «носятся».
"""

GEAR_TYPES = ("weapon", "armor", "helmet", "boots", "accessory")

RULES = {
    "max": 100,                # базовая прочность новых вещей
    "attack_hit": 1,           # оружие стачивается за свой удар
    "taken_hit": 1,            # слоты — за полученный удар
    "death": 7,                # смерть тратит прочность всего надетого
    # Ремонт: цена в бронзе за единицу нехватки прочности × множитель
    # редкости + один железный лом (материал 0) на ремонт.
    "cost_per": 2,
    "material": 0,
}

# Чем реже класс вещи, тем дороже чинить — «походный» хлам дешевле.
_RARITY_MULT = {"common": 1.0, "uncommon": 1.5, "rare": 2.5,
                "epic": 4.0, "legendary": 7.0}


def is_gear(it) -> bool:
    """Это вещь, у которой есть прочность? Принимает dict из rules.item."""
    return bool(it and it.get("type") in GEAR_TYPES)


def rarity_mult(rarity: str) -> float:
    return float(_RARITY_MULT.get(rarity, 1.0))


def broken(inst) -> bool:
    """Экземпляр «заклинило»: статы не работают и надеть нельзя."""
    if not inst:
        return False
    return int(inst.get("durability", 1) or 0) <= 0


def max_of(inst) -> int:
    return max(1, int(inst.get("durability_max") or RULES["max"]))


def cur(inst) -> int:
    return max(0, min(max_of(inst), int(inst.get("durability", max_of(inst)) or 0)))


def blocked(inst) -> bool:
    """Оставить бонусы экземпляра? False — сломанный не усиливает героя."""
    return not broken(inst)


def decay(store, p, kind="attack"):
    """Снять прочность с надетых вещей (браузерный стек).

    `attack` — стачивается оружие; `taken` — защитные слоты; `death` —
    всё надетое. Возвращает список строк-предупреждений (Uid сломался).
    """
    from engine import items
    warnings = []
    worn = getattr(p, "worn", None) or {}
    if not worn:
        return warnings
    slots = {"attack": ("weapon",), "taken": ("armor", "helmet", "boots",
                                              "accessory"),
             "death": ("weapon", "armor", "helmet", "boots", "accessory")}
    targets = slots.get(kind, ())
    for slot in targets:
        uid = worn.get(slot)
        if not uid:
            continue
        inst = items.get(store, uid) if store is not None else None
        if inst is None or not is_gear(inst):
            continue
        amount = (RULES["attack_hit"] if kind == "attack"
                  else RULES["taken_hit"] if kind == "taken"
                  else RULES["death"])
        was = int(inst.get("durability", max_of(inst)) or 0)
        new = max(0, was - int(amount))
        inst["durability"] = new
        if was > 0 and new <= 0:
            name = inst.get("name", "вещь")
            warnings.append(f"🔩 <b>{name}</b> заклинило! Почини в кузнице.")
    return warnings


def repair_cost(inst) -> int:
    missing = max(0, max_of(inst) - cur(inst))
    return max(1, int(round(missing * RULES["cost_per"] * rarity_mult(
        inst.get("rarity", "common")))))


def repair_materials(inst) -> dict:
    """Материалы на починку: {индекс: количество}."""
    return {int(RULES["material"]): 1}


def repair(inst, already_paid=True) -> dict:
    """Починить экземпляр до максимума. Возвращает (было, стало, цена)."""
    was = cur(inst)
    cost = repair_cost(inst)
    if was >= max_of(inst):
        return {"ok": False, "was": was, "now": was, "cost": 0,
                "reason": "в исправности"}
    inst["durability"] = max_of(inst)
    return {"ok": True, "was": was, "now": int(inst["durability"]), "cost": cost}


def card_line(inst) -> str:
    """Строка прочности для карточки/списка экземпляра."""
    if not is_gear(inst):
        return ""
    now, cap = cur(inst), max_of(inst)
    if broken(inst):
        return "🔩 <b>Прочность: 0/макс</b> — сломано, почини в кузнице!"
    icon = "🟩" if now >= cap * 0.7 else "🟨" if now >= cap * 0.3 else "🟥"
    return f"🔩 Прочность: {icon} {now}/{cap}"
