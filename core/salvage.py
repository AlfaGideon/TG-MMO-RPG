"""Разбор снаряжения: серверная часть.

Таблица выхода материалов общая для обоих стеков и живёт в
`engine/salvage.py`. Здесь остаётся работа с БД.
"""
from sqlalchemy import select

from engine import salvage as S
from core.models import Character, InventoryItem, Item, ItemInstance
from core.enums import ItemRarity


def get_salvage_yield(inv_item: InventoryItem) -> dict:
    """Расчёт выхода материалов при разборе предмета."""
    item = inv_item.item
    instance = inv_item.instance
    rarity = instance.rarity if instance else (item.rarity if item else ItemRarity.COMMON)
    upgrade_level = instance.upgrade_level if instance else 0
    return S.yield_for(rarity, upgrade_level)


async def salvage_item(session, character: Character, inv_item: InventoryItem) -> dict:
    """Разобрать предмет на материалы."""
    if inv_item.is_equipped:
        return {"ok": False, "reason": "Сначала сними экипированный предмет!"}
    if inv_item.character_id != character.id:
        return {"ok": False, "reason": "Это не твой предмет."}

    mat_yield = get_salvage_yield(inv_item)
    item_name = inv_item.display_name()

    # Удаляем предмет
    if inv_item.instance:
        await session.delete(inv_item.instance)
    await session.delete(inv_item)

    # Начисляем материалы игроку
    from core.models import Item, InventoryItem
    # Ищем или создаем материалы
    scrap_item = (await session.execute(select(Item).where(Item.name == "Ржавый лом"))).scalars().first()
    if not scrap_item:
        scrap_item = Item(name="Ржавый лом", description="Металлический лом для кузницы", item_type="material", price=5)
        session.add(scrap_item)
        await session.flush()

    session.add(InventoryItem(
        character_id=character.id,
        item_id=scrap_item.id,
        quantity=mat_yield["iron_scrap"],
    ))

    await session.flush()
    return {
        "ok": True,
        "item_name": item_name,
        "materials": mat_yield,
    }
