from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.database import async_session
from core.enums import ItemSource
from core.loot import grant_item
from core.models import User, Character, ShopItem, InventoryItem
from bot.keyboards.inline import shop_keyboard, main_menu_keyboard

router = Router()


@router.callback_query(F.data == "shop")
async def shop(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        result = await session.execute(
            select(ShopItem)
            .options(selectinload(ShopItem.item))
        )
        items = result.scalars().all()

        if not items:
            await callback.message.edit_text(
                "🏪 <b>Лавка торговца</b>\n\nСейчас товаров нет. Загляни позже.",
                reply_markup=main_menu_keyboard(has_character=True),
                parse_mode="HTML",
            )
            return

        await callback.message.edit_text(
            "🏪 <b>Лавка торговца</b>\n\nВыбери, что купить:",
            reply_markup=shop_keyboard(items),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("buy:"))
async def buy_item(callback: CallbackQuery):
    shop_item_id = int(callback.data.split(":")[1])
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
            select(ShopItem)
            .where(ShopItem.id == shop_item_id)
            .options(selectinload(ShopItem.item))
        )
        shop_item = result.scalar_one_or_none()
        if not shop_item:
            await callback.answer("Товар не найден.", show_alert=True)
            return

        if character.gold < shop_item.price:
            await callback.answer("Недостаточно золота!", show_alert=True)
            return

        if shop_item.stock == 0:
            await callback.answer("Товар распродан!", show_alert=True)
            return

        character.gold -= shop_item.price
        if shop_item.stock > 0:
            shop_item.stock -= 1

        # Купленное снаряжение — тоже уникальный экземпляр со своим ID,
        # но с меньшим разбросом: товар лавки заведомо «стандартный».
        await grant_item(
            session, character, shop_item.item, 1,
            source=ItemSource.SHOP.value,
            source_detail="Лавка торговца",
            extra_variance=-0.05,
        )

        await session.commit()

    await callback.answer(f"Куплено: {shop_item.item.name}")
    await shop(callback)
