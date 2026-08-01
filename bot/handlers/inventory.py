from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core import history
from core import stash as stash_core
from core.database import async_session
from core.models import (User, Character, InventoryItem, Item, ItemInstance,
                         Location)
from core.enums import ItemType
from core.stats import combat_stats
from bot.keyboards.inline import (
    inventory_keyboard, item_action_keyboard, main_menu_keyboard,
)
from bot.utils.texts import item_detail_text, item_line
from bot.utils.photos import send_or_edit_photo
from bot.utils.edit import safe_edit_text

router = Router()

# Расходники нельзя «надеть», их используют
EQUIPPABLE = {
    ItemType.WEAPON, ItemType.ARMOR, ItemType.HELMET,
    ItemType.BOOTS, ItemType.ACCESSORY,
}


async def load_inventory(session, character_id: int):
    """Инвентарь с подгруженными шаблонами и уникальными экземплярами."""
    result = await session.execute(
        select(InventoryItem)
        .where(InventoryItem.character_id == character_id)
        .options(
            selectinload(InventoryItem.item),
            selectinload(InventoryItem.instance).selectinload(ItemInstance.item),
        )
        .order_by(
            InventoryItem.is_equipped.desc(),
            InventoryItem.id,
        )
    )
    return result.scalars().all()


async def stash_summary(session, character) -> str:
    """Строка «сколько в кармане» для экрана инвентаря."""
    kept = len(await stash_core.stashed(session, character))
    cap = await stash_core.capacity(session, character)
    return f"🔒 Карман: {kept}/{cap}"


async def _character_of(session, telegram_id: int):
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        return None
    result = await session.execute(
        select(Character).where(Character.user_id == user.id)
    )
    return result.scalar_one_or_none()


def inventory_text(items, stats: dict) -> str:
    """Заголовок сумки: сводка по надетому + список."""
    equipped = [i for i in items if i.is_equipped]
    lines = [
        "🎒 <b>Инвентарь</b>",
        f"Предметов: {len(items)} | Надето: {len(equipped)}",
        "",
        f"⚔️ Урон от снаряжения: <b>+{stats['damage']}</b> | "
        f"🛡 Защита: <b>+{stats['defense']}</b>",
    ]
    bonus = stats["bonus"]
    extras = []
    for key, label in (
        ("strength", "💪"), ("agility", "🏃"), ("intelligence", "🧠"),
        ("endurance", "🛡"), ("luck", "🍀"), ("max_hp", "❤️"), ("max_mp", "💙"),
    ):
        if bonus.get(key):
            extras.append(f"{label} +{bonus[key]}")
    if extras:
        lines.append("Бонусы: " + " ".join(extras))
    lines.append("")
    lines.append("Выбери предмет:")
    return "\n".join(lines)


@router.callback_query(F.data == "inventory")
async def inventory(callback: CallbackQuery, page: int = 0):
    async with async_session() as session:
        character = await _character_of(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        items = await load_inventory(session, character.id)
        if not items:
            await safe_edit_text(callback, "🎒 <b>Инвентарь</b>\n\nТвоя сумка пуста...",
                reply_markup=main_menu_keyboard(has_character=True),
                parse_mode="HTML",
            )
            return

        stats = await combat_stats(session, character)
        pocket = await stash_summary(session, character)

    await safe_edit_text(
        callback,
        inventory_text(items, stats)
        + f"\n\n{pocket}\n<i>🎒 Сумка теряется при гибели, 🔒 карман — нет.</i>",
        reply_markup=inventory_keyboard(items, page=page),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("inv_page:"))
async def inventory_page(callback: CallbackQuery):
    page = int(callback.data.split(":")[1])
    await inventory(callback, page=page)


@router.callback_query(F.data.startswith("item:"))
async def item_detail(callback: CallbackQuery):
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.id == inv_id)
            .options(
                selectinload(InventoryItem.item),
                selectinload(InventoryItem.instance),
            )
        )
        inv_item = result.scalar_one_or_none()
        if not inv_item:
            await callback.answer("Предмет не найден.", show_alert=True)
            return

        item = inv_item.item
        # Летопись есть только у именных вещей
        rows = await history.load(session, inv_item.instance_id) \
            if inv_item.instance_id else []
        text = item_detail_text(inv_item, rows)
        can_equip = item.item_type in EQUIPPABLE
        can_use = item.item_type == ItemType.CONSUMABLE
        can_sell = bool(inv_item.instance_id) and item.is_sellable

        # Защищённый карман: убирать можно только в безопасных землях.
        character = await _character_of(session, callback.from_user.id)
        can_stash = False
        if character is not None:
            location = await session.get(Location, character.location_id)
            can_stash = (stash_core.safe_here(location)
                         and await stash_core.free_slots(session, character) > 0)
        if inv_item.in_stash:
            text += "\n\n🔒 <i>В защищённом кармане — не теряется при гибели.</i>"

    await send_or_edit_photo(
        callback,
        text,
        reply_markup=item_action_keyboard(
            inv_item.id, inv_item.is_equipped,
            can_equip=can_equip, can_use=can_use, can_sell=can_sell,
            in_stash=bool(inv_item.in_stash), can_stash=can_stash,
        ),
        image_url=item.image_url,
    )


@router.callback_query(F.data.startswith("stash_put:"))
async def stash_put(callback: CallbackQuery):
    """Убрать вещь в защищённый карман."""
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character_of(session, callback.from_user.id)
        inv_item = await session.get(InventoryItem, inv_id)
        if character is None or inv_item is None:
            await callback.answer("Предмет не найден.", show_alert=True)
            return
        location = await session.get(Location, character.location_id)
        if not stash_core.safe_here(location):
            await callback.answer(
                "Карман открывается только в безопасных землях.", show_alert=True)
            return
        ok, msg = await stash_core.put(session, character, inv_item)
        await session.commit()
    await callback.answer(msg, show_alert=not ok)
    if ok:
        await item_detail(callback)


@router.callback_query(F.data.startswith("stash_take:"))
async def stash_take(callback: CallbackQuery):
    """Достать вещь из кармана обратно в сумку."""
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character_of(session, callback.from_user.id)
        inv_item = await session.get(InventoryItem, inv_id)
        if character is None or inv_item is None:
            await callback.answer("Предмет не найден.", show_alert=True)
            return
        location = await session.get(Location, character.location_id)
        if not stash_core.safe_here(location):
            await callback.answer(
                "Карман открывается только в безопасных землях.", show_alert=True)
            return
        ok, msg = await stash_core.take(session, character, inv_item)
        await session.commit()
    await callback.answer(msg, show_alert=not ok)
    if ok:
        await item_detail(callback)


@router.callback_query(F.data.startswith("equip:"))
async def equip_item(callback: CallbackQuery):
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.id == inv_id)
            .options(
                selectinload(InventoryItem.item),
                selectinload(InventoryItem.instance),
            )
        )
        inv_item = result.scalar_one_or_none()
        if not inv_item:
            await callback.answer("Предмет не найден.", show_alert=True)
            return

        item = inv_item.item
        if item.item_type not in EQUIPPABLE:
            await callback.answer("Это нельзя надеть.", show_alert=True)
            return

        character = await session.get(Character, inv_item.character_id)
        if character.level < (item.level_requirement or 1):
            await callback.answer(
                f"Нужен {item.level_requirement} уровень!", show_alert=True
            )
            return

        # Снимаем то, что уже занимает этот слот
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.character_id == character.id)
            .where(InventoryItem.is_equipped == True)  # noqa: E712
            .options(selectinload(InventoryItem.item))
        )
        for eq in result.scalars().all():
            if eq.item.item_type == item.item_type:
                eq.is_equipped = False

        inv_item.is_equipped = True
        name = inv_item.display_name()
        await session.commit()

    await callback.answer(f"Экипировано: {name}")
    await inventory(callback)


@router.callback_query(F.data.startswith("unequip:"))
async def unequip_item(callback: CallbackQuery):
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        inv_item = await session.get(InventoryItem, inv_id)
        if inv_item:
            inv_item.is_equipped = False
            await session.commit()
    await callback.answer("Предмет снят.")
    await inventory(callback)


@router.callback_query(F.data.startswith("use:"))
async def use_item(callback: CallbackQuery):
    """Расходники: зелья восстанавливают HP/MP по своим бонусам."""
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.id == inv_id)
            .options(selectinload(InventoryItem.item))
        )
        inv_item = result.scalar_one_or_none()
        if not inv_item or inv_item.item.item_type != ItemType.CONSUMABLE:
            await callback.answer("Это нельзя использовать.", show_alert=True)
            return

        character = await session.get(Character, inv_item.character_id)
        item = inv_item.item
        bonuses = inv_item.bonuses()

        # Если у зелья не проставлены бонусы — лечим по редкости
        heal = bonuses.get("bonus_hp") or 0
        mana = bonuses.get("bonus_mp") or 0
        if not heal and not mana:
            base = {"common": 30, "uncommon": 70, "rare": 140}.get(
                item.rarity.value, 30
            )
            if "ман" in item.name.lower():
                mana = base
            else:
                heal = base

        before_hp, before_mp = character.current_hp, character.current_mp
        character.current_hp = min(character.max_hp, character.current_hp + heal)
        character.current_mp = min(character.max_mp, character.current_mp + mana)
        gained_hp = character.current_hp - before_hp
        gained_mp = character.current_mp - before_mp

        inv_item.quantity = (inv_item.quantity or 1) - 1
        if inv_item.quantity <= 0:
            await session.delete(inv_item)
        await session.commit()

    parts = []
    if gained_hp:
        parts.append(f"❤️ +{gained_hp} HP")
    if gained_mp:
        parts.append(f"💙 +{gained_mp} MP")
    await callback.answer(
        f"{item.name}: " + (" | ".join(parts) if parts else "эффекта нет"),
        show_alert=True,
    )
    await inventory(callback)


@router.callback_query(F.data.startswith("drop:"))
async def drop_item(callback: CallbackQuery):
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.id == inv_id)
            .options(selectinload(InventoryItem.instance))
        )
        inv_item = result.scalar_one_or_none()
        if inv_item:
            instance = inv_item.instance
            await session.delete(inv_item)
            # Уникальный экземпляр умирает вместе со строкой инвентаря
            if instance is not None:
                await session.delete(instance)
            await session.commit()
    await callback.answer("Предмет выброшен.")
    await inventory(callback)
