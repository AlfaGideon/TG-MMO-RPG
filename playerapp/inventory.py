"""Инвентарь игрока для мобильного API.

Правила экипировки повторяют bot/handlers/inventory.py: надеваемые типы —
оружие/броня/шлем/обувь/аксессуар, при надевании предыдущая вещь слота
снимается, расходники и материалы надеть нельзя.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.enums import ItemType
from core.models import Character, InventoryItem, Item
from playerapp.service import ServiceError

EQUIPPABLE = {
    ItemType.WEAPON, ItemType.ARMOR, ItemType.HELMET,
    ItemType.BOOTS, ItemType.ACCESSORY,
}

# Слот персонажа под каждый тип предмета (поля Character.<slot>_id)
_SLOT_FIELD = {
    ItemType.WEAPON: "weapon_id",
    ItemType.ARMOR: "armor_id",
    ItemType.HELMET: "helmet_id",
    ItemType.BOOTS: "boots_id",
    ItemType.ACCESSORY: "accessory_id",
}

_RARITY_RU = {
    "common": "Обычный", "uncommon": "Необычный", "rare": "Редкий",
    "epic": "Эпический", "legendary": "Легендарный",
}


def _item_dict(inv: InventoryItem) -> dict:
    item = inv.item
    return {
        "inventory_id": inv.id,
        "name": inv.display_name(),
        "type": getattr(item.item_type, "value", str(item.item_type)) if item else "",
        "rarity": _RARITY_RU.get(
            getattr(item.rarity, "value", "") if item else "",
            getattr(item.rarity, "value", "") if item else "",
        ),
        "quantity": inv.quantity,
        "equipped": bool(inv.is_equipped),
        "in_stash": bool(inv.in_stash),
        "in_home": bool(inv.in_home),
        "level_requirement": (item.level_requirement if item else 1) or 1,
        "uid": inv.uid(),
    }


async def list_inventory(session: AsyncSession, character: Character) -> dict:
    result = await session.execute(
        select(InventoryItem)
        .where(InventoryItem.character_id == character.id)
        .options(selectinload(InventoryItem.item),
                 selectinload(InventoryItem.instance))
        .order_by(InventoryItem.is_equipped.desc(), InventoryItem.id)
    )
    items = result.scalars().all()
    equipped = [_item_dict(i) for i in items if i.is_equipped]
    bag = [_item_dict(i) for i in items if not i.is_equipped and not i.in_stash and not i.in_home]
    stash = [_item_dict(i) for i in items if i.in_stash]
    home = [_item_dict(i) for i in items if i.in_home]
    return {"equipped": equipped, "bag": bag, "stash": stash, "home": home}


async def equip(session: AsyncSession, character: Character, inventory_id: int) -> dict:
    inv = await session.scalar(
        select(InventoryItem)
        .where(InventoryItem.id == inventory_id)
        .where(InventoryItem.character_id == character.id)
        .options(selectinload(InventoryItem.item))
    )
    if inv is None:
        raise ServiceError("Предмет не найден.")
    item = inv.item
    if item is None or item.item_type not in EQUIPPABLE:
        raise ServiceError("Это нельзя надеть.")
    if character.level < (item.level_requirement or 1):
        raise ServiceError(f"Нужен {item.level_requirement} уровень.")

    # Снимаем вещь, уже занимающую этот слот.
    equipped = await session.execute(
        select(InventoryItem)
        .where(InventoryItem.character_id == character.id)
        .where(InventoryItem.is_equipped.is_(True))
        .options(selectinload(InventoryItem.item))
    )
    for other in equipped.scalars().all():
        if other.item and other.item.item_type == item.item_type:
            other.is_equipped = False

    inv.is_equipped = True
    setattr(character, _SLOT_FIELD[item.item_type], item.id)
    await session.commit()
    return {"ok": True, "message": f"Экипировано: {inv.display_name()}",
            "inventory": await list_inventory(session, character)}


async def unequip(session: AsyncSession, character: Character, inventory_id: int) -> dict:
    inv = await session.scalar(
        select(InventoryItem)
        .where(InventoryItem.id == inventory_id)
        .where(InventoryItem.character_id == character.id)
        .options(selectinload(InventoryItem.item))
    )
    if inv is None:
        raise ServiceError("Предмет не найден.")
    if inv.is_equipped and inv.item:
        field = _SLOT_FIELD.get(inv.item.item_type)
        if field and getattr(character, field) == inv.item_id:
            setattr(character, field, None)
    inv.is_equipped = False
    await session.commit()
    return {"ok": True, "message": "Предмет снят.",
            "inventory": await list_inventory(session, character)}
