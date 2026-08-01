"""Лавки: обычная (у торговца на клетке) и лавка лекаря (VIP из меню).

Витрина устроена как книга: одна страница — один товар с описанием,
свойствами и ценой. Список строк «название — цена» ничего не рассказывал
о вещи, и игрок покупал вслепую.

Обычная лавка убрана из главного меню: за товаром надо дойти до торговца.
Лавка лекаря — VIP-удобство: зелья доступны из меню в любой момент.
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from core.database import async_session
from core.enums import ItemSource, ItemType
from core.loot import grant_item
from core.models import User, Character, ShopItem, InventoryItem, Item
from core.vip import is_vip_active
from bot.keyboards.inline import (shop_book_keyboard, back_to_main_keyboard,
                                  main_menu_keyboard)
from bot.utils.texts import item_book_text
from bot.utils.edit import safe_edit_text

router = Router()

# Лекарь торгует только расходниками — зельями и снадобьями.
HEALER_TYPES = (ItemType.CONSUMABLE,)


async def _character(session, telegram_id: int):
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        return None
    result = await session.execute(
        select(Character).where(Character.user_id == user.id)
    )
    return result.scalar_one_or_none()


async def _stock(session, healer_only: bool = False):
    query = (
        select(ShopItem)
        .join(Item, ShopItem.item_id == Item.id)
        .options(selectinload(ShopItem.item))
        .order_by(Item.item_type, Item.price, ShopItem.id)
    )
    if healer_only:
        query = query.where(Item.item_type.in_(HEALER_TYPES))
    result = await session.execute(query)
    return [si for si in result.scalars().all() if si.item is not None]


async def _owned(session, character, item_id: int) -> int:
    """Сколько таких предметов уже лежит в сумке — видно прямо на странице."""
    total = await session.scalar(
        select(func.coalesce(func.sum(InventoryItem.quantity), 0))
        .where(InventoryItem.character_id == character.id)
        .where(InventoryItem.item_id == item_id)
    )
    return int(total or 0)


async def _render_book(callback: CallbackQuery, page: int, healer: bool):
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if character is None:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        if healer and not is_vip_active(character):
            await callback.answer(
                "⚗️ Лавка лекаря открыта только для VIP.", show_alert=True)
            return

        items = await _stock(session, healer_only=healer)
        header = "⚗️ Лавка лекаря" if healer else "🏪 Лавка торговца"
        page_cb = "healer_page" if healer else "shop_page"
        back_cb = "main_menu" if healer else "back_to_cell"
        back_text = "🏠 Меню" if healer else "◀️ Уйти от торговца"

        if not items:
            await safe_edit_text(
                callback,
                f"{header}\n\nПрилавок пуст. Загляни позже.",
                reply_markup=(main_menu_keyboard(has_character=True, is_vip=True)
                              if healer else back_to_main_keyboard()),
                parse_mode="HTML",
            )
            return

        from engine.currency import total_in_bronze, currency_str, CONVERSION
        page = max(0, min(page, len(items) - 1))
        shop_item = items[page]
        owned = await _owned(session, character, shop_item.item_id)
        sold_out = shop_item.stock == 0
        affordable = total_in_bronze(character) >= shop_item.price

        note = f"💰 У тебя: <b>{currency_str(character)}</b>"
        if sold_out:
            note += "\n<i>Этот товар уже разобрали.</i>"
        elif not affordable:
            missing = shop_item.price - total_in_bronze(character)
            g_val = missing // (CONVERSION * CONVERSION)
            remainder = missing % (CONVERSION * CONVERSION)
            s_val = remainder // CONVERSION
            b_val = remainder % CONVERSION
            missing_parts = []
            if g_val > 0:
                missing_parts.append(f"{g_val}🪙")
            if s_val > 0:
                missing_parts.append(f"{s_val}🥈")
            if b_val > 0 or not missing_parts:
                missing_parts.append(f"{b_val}🪙")
            missing_str = " ".join(missing_parts)
            note += f"\n<i>Не хватает {missing_str}.</i>"

        text = item_book_text(
            shop_item.item, page, len(items), header=header,
            price=shop_item.price, stock=shop_item.stock, owned=owned,
            note=note,
        )

    await safe_edit_text(
        callback,
        text,
        reply_markup=shop_book_keyboard(
            shop_item, page, len(items),
            can_buy=affordable and not sold_out,
            page_cb=page_cb, back_cb=back_cb, back_text=back_text,
        ),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "shop")
async def shop(callback: CallbackQuery):
    await _render_book(callback, 0, healer=False)


@router.callback_query(F.data.startswith("shop_page:"))
async def shop_page(callback: CallbackQuery):
    await _render_book(callback, int(callback.data.split(":")[1]), healer=False)


@router.callback_query(F.data == "healer_shop")
async def healer_shop(callback: CallbackQuery):
    await _render_book(callback, 0, healer=True)


@router.callback_query(F.data.startswith("healer_page:"))
async def healer_page(callback: CallbackQuery):
    await _render_book(callback, int(callback.data.split(":")[1]), healer=True)


@router.callback_query(F.data.startswith("buy:"))
async def buy_item(callback: CallbackQuery):
    shop_item_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if character is None:
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

        from engine.currency import total_in_bronze, deduct_currency
        if total_in_bronze(character) < shop_item.price:
            await callback.answer("Недостаточно средств!", show_alert=True)
            return

        if shop_item.stock == 0:
            await callback.answer("Товар распродан!", show_alert=True)
            return

        healer = shop_item.item.item_type in HEALER_TYPES
        deduct_currency(character, shop_item.price)
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

        name = shop_item.item.name
        items = await _stock(session, healer_only=healer)
        page = next((i for i, si in enumerate(items) if si.id == shop_item.id), 0)
        await session.commit()

    await callback.answer(f"Куплено: {name}")
    # Остаёмся на той же странице книги, а не выпадаем в меню.
    await _render_book(callback, page, healer=healer)
