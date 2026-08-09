"""Стол публичных ремесленных заказов: заказчики предоставляют награду, мастера куют предметы."""
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.models import Character, CraftOrder, CraftRecipe, InventoryItem, ItemInstance
from core.crafting import _count_material, _consume_material, craft


def _now():
    return datetime.now(timezone.utc)


async def list_open_orders(session) -> list[CraftOrder]:
    """Список всех открытых публичных заказов."""
    result = await session.execute(
        select(CraftOrder)
        .where(CraftOrder.status == "open")
        .options(selectinload(CraftOrder.recipe), selectinload(CraftOrder.creator))
        .order_by(CraftOrder.created_at.desc())
    )
    return result.scalars().all()


async def create_order(session, character: Character, recipe_id: int, bounty_bronze: int) -> dict:
    """Создать публичный ремесленный заказ."""
    from engine.currency import total_in_bronze, deduct_currency

    recipe = await session.get(CraftRecipe, recipe_id)
    if not recipe:
        return {"ok": False, "reason": "Рецепт не найден."}

    min_bounty = 100
    if bounty_bronze < min_bounty:
        return {"ok": False, "reason": f"Минимальная награда за заказ — {min_bounty}🟤."}

    total_cost = (recipe.gold_cost or 0) + bounty_bronze
    if total_in_bronze(character) < total_cost:
        return {"ok": False, "reason": f"Не хватает средств! Требуется {total_cost}🟤 (включая работу мастера)."}

    # Списываем золото у заказчика (кладём в депозит заказа)
    deduct_currency(character, total_cost)

    order = CraftOrder(
        creator_character_id=character.id,
        recipe_id=recipe.id,
        reward_bronze=bounty_bronze,
        status="open",
    )
    session.add(order)
    await session.flush()
    return {"ok": True, "order": order}


async def fulfill_order(session, crafter: Character, order_id: int) -> dict:
    """Мастер выполняет заказ, получает гонорар, а вещь отправляется заказчику."""
    from engine.currency import add_currency

    result = await session.execute(
        select(CraftOrder)
        .where(CraftOrder.id == order_id)
        .options(selectinload(CraftOrder.recipe), selectinload(CraftOrder.creator))
    )
    order = result.scalar_one_or_none()
    if not order or order.status != "open":
        return {"ok": False, "reason": "Заказ уже выполнен или отменён."}

    if order.creator_character_id == crafter.id:
        return {"ok": False, "reason": "Нельзя выполнять собственный заказ."}

    recipe = order.recipe
    if crafter.level < (recipe.min_level or 1):
        return {"ok": False, "reason": f"Для этого рецепта требуется {recipe.min_level} уровень кузнеца."}

    # Крафтим вещь (материалы мастера)
    res = await craft(session, crafter, recipe)
    if not res["ok"]:
        return res

    instance = res["instance"]
    # Передаём вещь заказчику
    instance.owner_character_id = order.creator_character_id
    # Забираем из инвентаря мастера и добавляем заказчику
    inv_item = (await session.execute(
        select(InventoryItem).where(InventoryItem.instance_id == instance.id)
    )).scalar_one_or_none()
    if inv_item:
        inv_item.character_id = order.creator_character_id

    # Мастер получает вознаграждение бронзой
    add_currency(crafter, bronze=order.reward_bronze)
    crafter.experience = (crafter.experience or 0) + 150

    order.status = "completed"
    order.completed_by_character_id = crafter.id
    order.completed_at = _now()
    await session.flush()

    return {
        "ok": True,
        "reward": order.reward_bronze,
        "instance": instance,
        "creator_name": order.creator.name if order.creator else "Заказчик",
    }
