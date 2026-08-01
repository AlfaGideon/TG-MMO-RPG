"""Крафт и улучшение предметов гриндом.

NPC-ремесленник (кузнец / алхимик / ювелир) стоит на клетке карты и даёт
два сервиса:

* **Крафт** — по рецепту из `craft_recipes` тратятся материалы и золото,
  на выходе получается *уникальный* экземпляр предмета со своими статами.
* **Заточка** — существующий экземпляр улучшается за золото и материалы,
  добытые гриндом. Каждый уровень поднимает статы; при неудаче уровень не
  теряется, но ресурсы сгорают.
"""
import random

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core import history
from core.enums import CraftStation, ItemSource
from core.loot import (
    apply_upgrade, create_instance, find_upgrade_rule, is_stackable,
)
from core.models import (
    CraftIngredient, CraftRecipe, InventoryItem, Item, ItemInstance,
)


async def recipes_for_station(session, station: str | None):
    """Активные рецепты станка. `None`/`any` — весь список."""
    query = (
        select(CraftRecipe)
        .options(
            selectinload(CraftRecipe.result_item),
            selectinload(CraftRecipe.ingredients).selectinload(CraftIngredient.item),
        )
        .where(CraftRecipe.is_enabled == True)  # noqa: E712
        .order_by(CraftRecipe.min_level, CraftRecipe.id)
    )
    if station and station != CraftStation.ANY.value:
        query = query.where(
            CraftRecipe.station.in_([station, CraftStation.ANY.value])
        )
    result = await session.execute(query)
    return result.scalars().all()


async def _count_material(session, character_id: int, item_id: int) -> int:
    """Сколько у игрока этого материала (стопки + отдельные экземпляры)."""
    result = await session.execute(
        select(InventoryItem)
        .where(InventoryItem.character_id == character_id)
        .where(InventoryItem.item_id == item_id)
    )
    rows = result.scalars().all()
    return sum(r.quantity or 0 for r in rows if not r.is_equipped)


async def _consume_material(session, character_id: int, item_id: int, amount: int) -> bool:
    """Списывает материалы. Экипированное не трогает."""
    result = await session.execute(
        select(InventoryItem)
        .where(InventoryItem.character_id == character_id)
        .where(InventoryItem.item_id == item_id)
        .order_by(InventoryItem.instance_id.is_(None).desc())
    )
    rows = [r for r in result.scalars().all() if not r.is_equipped]
    left = amount
    for row in rows:
        if left <= 0:
            break
        take = min(left, row.quantity or 0)
        row.quantity = (row.quantity or 0) - take
        left -= take
        if row.quantity <= 0:
            await session.delete(row)
    await session.flush()
    return left <= 0


async def check_recipe(session, character, recipe: CraftRecipe) -> dict:
    """Что не хватает для крафта. Возвращает сводку для UI."""
    from engine.currency import total_in_bronze
    missing = []
    for ing in recipe.ingredients:
        have = await _count_material(session, character.id, ing.item_id)
        if have < (ing.quantity or 1):
            missing.append({
                "item": ing.item, "need": ing.quantity or 1, "have": have,
            })
    gold_bal = total_in_bronze(character)
    return {
        "can_craft": (
            not missing
            and gold_bal >= (recipe.gold_cost or 0)
            and character.level >= (recipe.min_level or 1)
        ),
        "missing": missing,
        "needs_gold": max(0, (recipe.gold_cost or 0) - gold_bal),
        "needs_level": max(0, (recipe.min_level or 1) - character.level),
    }


async def craft(session, character, recipe: CraftRecipe) -> dict:
    """Выполняет крафт. Возвращает {'ok', 'reason', 'instances'}."""
    status = await check_recipe(session, character, recipe)
    if not status["can_craft"]:
        if status["needs_level"]:
            return {"ok": False, "reason": f"Нужен {recipe.min_level} уровень."}
        if status["needs_gold"]:
            return {"ok": False, "reason": f"Не хватает {status['needs_gold']} золота."}
        names = ", ".join(
            f"{m['item'].name} ({m['have']}/{m['need']})" for m in status["missing"]
        )
        return {"ok": False, "reason": f"Не хватает материалов: {names}"}

    for ing in recipe.ingredients:
        await _consume_material(session, character.id, ing.item_id, ing.quantity or 1)
    from engine.currency import deduct_currency
    deduct_currency(character, recipe.gold_cost or 0)

    if random.random() > (recipe.success_chance or 1.0):
        await session.flush()
        return {
            "ok": False, "failed_roll": True,
            "reason": "Работа не удалась — материалы испорчены.",
            "instances": [],
        }

    item = recipe.result_item
    made = []
    for _ in range(max(1, recipe.result_quantity or 1)):
        if is_stackable(item):
            result = await session.execute(
                select(InventoryItem)
                .options(selectinload(InventoryItem.item))
                .where(InventoryItem.character_id == character.id)
                .where(InventoryItem.item_id == item.id)
                .where(InventoryItem.instance_id.is_(None))
            )
            row = result.scalar_one_or_none()
            if row:
                row.quantity = (row.quantity or 0) + 1
            else:
                stack = InventoryItem(
                    character_id=character.id, item_id=item.id, quantity=1,
                )
                stack.item = item
                session.add(stack)
            made.append(None)
            continue

        inst = create_instance(
            item,
            source=ItemSource.CRAFT.value,
            source_detail=recipe.name,
            extra_variance=recipe.quality_bonus or 0.0,
            luck=character.luck or 0,
        )
        inst.owner_character_id = character.id
        session.add(inst)
        await session.flush()
        await history.record_birth(session, inst, character, recipe.name)
        row = InventoryItem(
            character_id=character.id, item_id=item.id,
            instance_id=inst.id, quantity=1,
        )
        row.item = item
        row.instance = inst
        session.add(row)
        made.append(inst)

    await session.flush()
    return {"ok": True, "instances": [m for m in made if m], "item": item}


async def upgrade_cost(session, instance: ItemInstance, item: Item) -> dict | None:
    """Что нужно для следующего уровня заточки (или None, если предел)."""
    level = instance.upgrade_level or 0
    if level >= (item.max_upgrade_level or 10):
        return None
    rule = await find_upgrade_rule(session, level)
    if rule is None:
        return None
    return {
        "rule": rule,
        "gold": rule.gold_cost or 0,
        "material": rule.material_item,
        "material_qty": rule.material_quantity or 0,
        "chance": rule.success_chance or 1.0,
        "next_level": level + 1,
    }


async def upgrade(session, character, inv_item: InventoryItem) -> dict:
    """Улучшает предмет гриндом. Ресурсы тратятся даже при неудаче."""
    instance = inv_item.instance
    item = inv_item.item
    if instance is None:
        return {"ok": False, "reason": "Этот предмет нельзя улучшать."}

    cost = await upgrade_cost(session, instance, item)
    if cost is None:
        return {"ok": False, "reason": "Предмет достиг предела заточки."}

    from engine.currency import total_in_bronze, deduct_currency
    if total_in_bronze(character) < cost["gold"]:
        return {"ok": False, "reason": f"Не хватает {cost['gold'] - total_in_bronze(character)} золота."}

    if cost["material"] is not None and cost["material_qty"] > 0:
        have = await _count_material(session, character.id, cost["material"].id)
        if have < cost["material_qty"]:
            return {
                "ok": False,
                "reason": (
                    f"Нужно {cost['material'].name} "
                    f"×{cost['material_qty']} (есть {have})."
                ),
            }
        await _consume_material(
            session, character.id, cost["material"].id, cost["material_qty"]
        )

    deduct_currency(character, cost["gold"])

    if random.random() > cost["chance"]:
        await session.flush()
        return {
            "ok": False, "failed_roll": True,
            "reason": "Заточка сорвалась. Уровень предмета не изменился.",
            "level": instance.upgrade_level or 0,
        }

    gains = apply_upgrade(instance, item, cost["rule"])
    await history.record(
        session, instance, "upgraded", character,
        detail=f"до +{instance.upgrade_level}", price=cost["gold"],
    )
    await session.flush()
    return {"ok": True, "gains": gains, "level": instance.upgrade_level}
