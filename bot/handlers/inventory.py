from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.database import async_session
from core.models import User, Character, InventoryItem, Item
from core.enums import ItemType
from bot.keyboards.inline import inventory_keyboard, item_action_keyboard, main_menu_keyboard
from bot.utils.photos import send_or_edit_photo

router = Router()


@router.callback_query(F.data == "inventory")
async def inventory(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        result = await session.execute(
            select(Character).where(Character.user_id == user.id)
        )
        character = result.scalar_one_or_none()
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.character_id == character.id)
            .options(selectinload(InventoryItem.item))
        )
        items = result.scalars().all()

        if not items:
            await callback.message.edit_text(
                "🎒 <b>Инвентарь</b>\n\nТвоя сумка пуста...",
                reply_markup=main_menu_keyboard(has_character=True),
                parse_mode="HTML",
            )
            return

        await callback.message.edit_text(
            "🎒 <b>Инвентарь</b>\n\nВыбери предмет:",
            reply_markup=inventory_keyboard(items),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("inv_page:"))
async def inventory_page(callback: CallbackQuery):
    page = int(callback.data.split(":")[1])
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        result = await session.execute(
            select(Character).where(Character.user_id == user.id)
        )
        character = result.scalar_one_or_none()

        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.character_id == character.id)
            .options(selectinload(InventoryItem.item))
        )
        items = result.scalars().all()

    await callback.message.edit_text(
        "🎒 <b>Инвентарь</b>\n\nВыбери предмет:",
        reply_markup=inventory_keyboard(items, page=page),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("item:"))
async def item_detail(callback: CallbackQuery):
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.id == inv_id)
            .options(selectinload(InventoryItem.item))
        )
        inv_item = result.scalar_one_or_none()
        if not inv_item:
            await callback.answer("Предмет не найден.", show_alert=True)
            return

        item = inv_item.item
        text = (
            f"{item.icon} <b>{item.name}</b>\n"
            f"Тип: <code>{item.item_type.value}</code> | Редкость: <code>{item.rarity.value}</code>\n\n"
            f"{item.description}\n\n"
        )
        bonuses = []
        if item.bonus_strength: bonuses.append(f"💪 Сила +{item.bonus_strength}")
        if item.bonus_agility: bonuses.append(f"🏃 Ловкость +{item.bonus_agility}")
        if item.bonus_intelligence: bonuses.append(f"🧠 Интеллект +{item.bonus_intelligence}")
        if item.bonus_endurance: bonuses.append(f"🛡 Выносливость +{item.bonus_endurance}")
        if item.bonus_luck: bonuses.append(f"🍀 Удача +{item.bonus_luck}")
        if item.bonus_hp: bonuses.append(f"❤️ HP +{item.bonus_hp}")
        if item.bonus_mp: bonuses.append(f"💙 MP +{item.bonus_mp}")
        if item.bonus_damage: bonuses.append(f"⚔️ Урон +{item.bonus_damage}")
        if item.bonus_defense: bonuses.append(f"🛡 Защита +{item.bonus_defense}")

        if bonuses:
            text += "<b>Бонусы:</b>\n" + "\n".join(bonuses)
        else:
            text += "<b>Нет бонусов</b>"

        await send_or_edit_photo(
            callback,
            text,
            reply_markup=item_action_keyboard(inv_item.id, inv_item.is_equipped),
            image_url=item.image_url,
        )


@router.callback_query(F.data.startswith("equip:"))
async def equip_item(callback: CallbackQuery):
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.id == inv_id)
            .options(selectinload(InventoryItem.item))
        )
        inv_item = result.scalar_one_or_none()
        if not inv_item:
            await callback.answer("Предмет не найден.", show_alert=True)
            return

        item = inv_item.item
        result = await session.execute(
            select(Character).where(Character.id == inv_item.character_id)
        )
        character = result.scalar_one()

        if character.level < item.level_requirement:
            await callback.answer(f"Нужен {item.level_requirement} уровень!", show_alert=True)
            return

        # Unequip existing item of same type
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.character_id == character.id)
            .where(InventoryItem.is_equipped == True)
            .options(selectinload(InventoryItem.item))
        )
        equipped = result.scalars().all()
        for eq in equipped:
            if eq.item.item_type == item.item_type:
                eq.is_equipped = False

        inv_item.is_equipped = True
        await session.commit()

    await callback.answer(f"Экипировано: {item.name}")
    await inventory(callback)


@router.callback_query(F.data.startswith("unequip:"))
async def unequip_item(callback: CallbackQuery):
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        result = await session.execute(
            select(InventoryItem).where(InventoryItem.id == inv_id)
        )
        inv_item = result.scalar_one_or_none()
        if inv_item:
            inv_item.is_equipped = False
            await session.commit()
    await callback.answer("Предмет снят.")
    await inventory(callback)


@router.callback_query(F.data.startswith("drop:"))
async def drop_item(callback: CallbackQuery):
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        result = await session.execute(
            select(InventoryItem).where(InventoryItem.id == inv_id)
        )
        inv_item = result.scalar_one_or_none()
        if inv_item:
            await session.delete(inv_item)
            await session.commit()
    await callback.answer("Предмет выброшен.")
    await inventory(callback)
