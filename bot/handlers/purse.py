"""Кошелёк героя: разряды монет и обмен премиум-валюты.

Паритет с браузерным стеком (`engine/money.purse`): те же разряды, тот же
курс, та же однонаправленность обмена — кристаллы меняются на монеты, но
не наоборот.
"""
from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from core import money
from core.database import async_session
from core.models import Character, User
from engine.money import EXCHANGE_STEPS

router = Router()


async def _character(session, telegram_id):
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        return None
    result = await session.execute(
        select(Character).where(Character.user_id == user.id))
    return result.scalar_one_or_none()


def _keyboard(gems, rate):
    builder = InlineKeyboardBuilder()
    steps = [n for n in EXCHANGE_STEPS if rate > 0 and gems >= n]
    for n in steps:
        builder.button(text=f"{n}{money.PREMIUM_ICON}→", callback_data=f"gem_exchange:{n}")
    builder.adjust(len(steps) or 1)
    builder.row()
    builder.button(text="🧙 Профиль", callback_data="profile")
    builder.button(text="◀️ Меню", callback_data="main_menu")
    return builder.as_markup()


def _text(character, rate):
    g, s, b = money.split(money.balance(character))
    gems = money.premium(character)
    lines = [
        "👛 <b>Кошелёк</b>", "",
        f"{money.COINS[0][1]} Золотых: <b>{g}</b>",
        f"{money.COINS[1][1]} Серебряных: <b>{s}</b>",
        f"{money.COINS[2][1]} Бронзовых: <b>{b}</b>",
        "",
        f"{money.PREMIUM_ICON} {money.PREMIUM_NAME.capitalize()}: <b>{gems}</b>",
        "",
        f"<i>{money.coin_line()}</i>",
    ]
    lines.append(f"<i>Обмен: 1{money.PREMIUM_ICON} = {money.fmt(rate)}</i>"
                 if rate > 0 else "<i>Обмен кристаллов закрыт.</i>")
    return "\n".join(lines)


@router.callback_query(F.data == "purse")
async def purse(callback: CallbackQuery):
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if character is None:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        rate = await money.tune(session, "premium_rate")
        text = _text(character, rate)
        markup = _keyboard(money.premium(character), rate)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data.startswith("gem_exchange:"))
async def gem_exchange(callback: CallbackQuery):
    gems = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if character is None:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        ok, msg = await money.exchange(session, character, gems)
        rate = await money.tune(session, "premium_rate")
        text = _text(character, rate)
        markup = _keyboard(money.premium(character), rate)
    await callback.answer(msg, show_alert=not ok)
    if ok:
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
