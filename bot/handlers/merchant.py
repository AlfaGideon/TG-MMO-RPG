"""Бродячий торговец: витрина-книга, покупка диковинок.

Торговец появляется в локации на несколько часов (запускается админом
или приходит сам — см. core/merchant.py). Игрок, оказавшийся с ним в
одной локации, видит кнопку «🧳 Торговец» на экране клетки. Витрина —
книга, как в лавке: одна страница — один товар с карточкой и ценой.
"""
from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core import merchant
from core.database import async_session
from core.models import Character, User
from bot.keyboards.inline import merchant_book_keyboard
from bot.utils.edit import safe_edit_text
from bot.utils.texts import item_book_text

router = Router()


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


async def _render_book(callback: CallbackQuery, page: int):
    """Страница-книга: карточка одного товара со стрелками листания."""
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if character is None:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        wares = await merchant.wares(session)
        if not wares:
            await callback.answer("🧳 Торговец уже ушёл.", show_alert=True)
            return
        # Торговец должен стоять в локации игрока.
        state = await merchant.load(session)
        if not state or int(state.get("location_id") or 0) != character.location_id:
            await callback.answer("🧳 Торговца здесь нет — он ушёл.", show_alert=True)
            return
        from engine.currency import total_in_bronze, currency_str, CONVERSION
        page = max(0, min(page, len(wares) - 1))
        ware = wares[page]
        sold_out = ware["qty"] <= 0
        affordable = total_in_bronze(character) >= ware["price"]
        note = f"💰 У тебя: <b>{currency_str(character)}</b>"
        if sold_out:
            note += "\n<i>Этот товар уже разобрали.</i>"
        elif not affordable:
            missing = ware["price"] - total_in_bronze(character)
            g_val = missing // (CONVERSION * CONVERSION)
            remainder = missing % (CONVERSION * CONVERSION)
            s_val = remainder // CONVERSION
            b_val = remainder % CONVERSION
            missing_parts = []
            if g_val > 0:
                missing_parts.append(f"{g_val}🟡")
            if s_val > 0:
                missing_parts.append(f"{s_val}⚪")
            if b_val > 0 or not missing_parts:
                missing_parts.append(f"{b_val}🟤")
            missing_str = " ".join(missing_parts)
            note += f"\n<i>Не хватает {missing_str}.</i>"
        text = item_book_text(
            ware["item"], page, len(wares),
            header="🧳 Бродячий торговец",
            price=ware["price"], stock=ware["qty"], owned=0, note=note,
        )
    await safe_edit_text(
        callback,
        text,
        reply_markup=merchant_book_keyboard(
            ware, page, len(wares), can_buy=affordable and not sold_out),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "merchant_menu")
async def merchant_menu(callback: CallbackQuery):
    await _render_book(callback, 0)


@router.callback_query(F.data.startswith("merchant_page:"))
async def merchant_page(callback: CallbackQuery):
    await _render_book(callback, int(callback.data.split(":")[1]))


@router.callback_query(F.data.startswith("merchant_buy:"))
async def merchant_buy(callback: CallbackQuery):
    index = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if character is None:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        res = await merchant.buy(session, character, index)
        await session.commit()
    if not res["ok"]:
        await callback.answer(res["reason"], show_alert=True)
        return
    await callback.answer(
        f"Куплено: {res['item'].name} за {res['price']}🟤", show_alert=True)
    await _render_book(callback, index)
