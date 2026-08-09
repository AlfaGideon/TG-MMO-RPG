"""Переработка и утилизация снаряжения на ремесленные материалы."""
from sqlalchemy import select
from core.models import Character, InventoryItem, Item, ItemInstance
from core.enums import ItemRarity


def get_salvage_yield(inv_item: InventoryItem) -> dict:
    """Расчёт выхода материалов при разборе предмета."""
    item = inv_item.item
    instance = inv_item.instance
    rarity = instance.rarity if instance else (item.rarity if item else ItemRarity.COMMON)
    upgrade_level = instance.upgrade_level if instance else 0

    base_scrap = 2
    if rarity in (ItemRarity.UNCOMMON, "uncommon"):
        base_scrap = 4
    elif rarity in (ItemRarity.RARE, "rare"):
        base_scrap = 8
    elif rarity in (ItemRarity.EPIC, "epic"):
        base_scrap = 15
    elif rarity in (ItemRarity.LEGENDARY, "legendary"):
        base_scrap = 30

    base_scrap += upgrade_level * 3
    steel_bars = max(0, upgrade_level // 2)
    magic_dust = 1 if rarity in (ItemRarity.RARE, ItemRarity.EPIC, ItemRarity.LEGENDARY, "rare", "epic", "legendary") else 0

    return {
        "iron_scrap": base_scrap,
        "steel_bars": steel_bars,
        "magic_dust": magic_dust,
    }


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
