"""Торги с молотка: витрина, ставки, выкуп (IDEAS-100.md № 59).

Отдельный роутер, а не дописка в `bot/handlers/auction.py`: тот файл уже
523 строки при лимите 500 (`tests/test_wiring.py`), и торги — самостоятельный
сценарий со своими экранами.

Вся логика денег и гонок живёт в `core/auction_bid.py`. Здесь только экраны
и уведомления: перебитому лидеру приходит весть о возврате резерва, иначе
он узнал бы о проигрыше, только заглянув в аукцион.
"""
from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot.utils.edit import safe_edit_text
from core import auction_bid as B
from core.database import async_session
from core.models import AuctionLot, Character, InventoryItem, User

router = Router()

PER_PAGE = 6


async def _character(session, telegram_id: int):
    return (await session.execute(
        select(Character).join(User).where(User.telegram_id == telegram_id)
    )).scalars().first()


async def _notify(character_id: int, text: str):
    """Личное сообщение игроку. Молчит, если бот остановлен."""
    if not character_id:
        return
    try:
        from bot.runner import bot_runner

        if not (bot_runner.is_running() and bot_runner.bot):
            return
        async with async_session() as session:
            character = await session.get(Character, character_id)
            if character is None:
                return
            user = await session.get(User, character.user_id)
            if user is None:
                return
            tg_id = user.telegram_id
        await bot_runner.bot.send_message(chat_id=tg_id, text=text,
                                          parse_mode="HTML")
    except Exception:
        pass


def _back_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔨 К торгам", callback_data="bids_menu")
    builder.button(text="◀️ Аукцион", callback_data="auction_menu")
    builder.adjust(1)
    return builder.as_markup()


@router.callback_query(F.data == "bids_menu")
async def bids_menu(callback: CallbackQuery):
    """🔨 Витрина торгов: что уходит с молотка прямо сейчас."""
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if character is None:
            await callback.answer("Сначала создай героя.", show_alert=True)
            return

        # Молоток бьёт и здесь: истёкшие торги закрываются при каждом заходе,
        # а не только фоновым циклом — иначе на витрине висели бы мертвецы.
        finished = await B.close_finished(session)
        await session.commit()

        lots = await B.active_bid_lots(session)
        my_leading = await B.my_bids(session, character.id)
        reserved = await B.reserved_total(session, character.id)
        rows = []
        for lot in lots:
            item = await session.get(__import__("core.models",
                                                fromlist=["Item"]).Item,
                                     lot.item_id)
            rows.append((lot, item))

    for res in finished:
        if res.get("sold"):
            await _notify(res.get("winner_id"),
                          f"🔨 <b>Молоток!</b> Лот твой за {res['amount']}🟤 — "
                          f"вещь уже в сумке.")
            await _notify(res.get("seller_id"),
                          f"💰 <b>Твой лот ушёл с молотка</b> за "
                          f"{res['amount']}🟤. На руки: {res['payout']}🟤.")
        else:
            await _notify(res.get("seller_id"),
                          "🔨 <b>Торги закончились без ставок</b> — "
                          "вещь вернулась в сумку.")

    lines = ["🔨 <b>Торги с молотка</b>", "",
             "<i>Цена растёт, пока идут ставки. Вещь уходит последнему, "
             "кто поднял.</i>", ""]
    if reserved:
        lines.append(f"🔒 В твоих ставках заморожено: <b>{reserved}</b>🟤")
        lines.append(f"<i>Лидируешь в торгах: {len(my_leading)}.</i>")
        lines.append("")

    builder = InlineKeyboardBuilder()
    if not rows:
        lines.append("<i>Сейчас с молотка ничего не уходит.</i>")
    for lot, item in rows[:PER_PAGE]:
        name = item.name if item else "лот"
        icon = (item.icon if item and item.icon else "❔")
        lines.append(f"{icon} <b>{name}</b> — {B.lot_line(lot)}")
        builder.button(text=f"{icon} {name} · {B.next_bid(lot)}🟤",
                       callback_data=f"bid_lot:{lot.id}")

    builder.button(text="📢 Выставить с молотка", callback_data="bid_sell:0")
    builder.button(text="◀️ Аукцион", callback_data="auction_menu")
    builder.adjust(1)

    await safe_edit_text(callback, "\n".join(lines),
                         reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("bid_lot:"))
async def bid_lot(callback: CallbackQuery):
    """Карточка лота: история торга и кнопки ставки."""
    lot_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        lot = (await session.execute(
            select(AuctionLot).where(AuctionLot.id == lot_id)
            .options(selectinload(AuctionLot.item),
                     selectinload(AuctionLot.instance))
        )).scalar_one_or_none()
        if lot is None or character is None:
            await callback.answer("Лот не найден.", show_alert=True)
            return
        item, inst = lot.item, lot.instance
        name = inst.display_name(item) if inst else (item.name if item else "лот")
        uid = inst.tagged_uid() if inst else ""
        required = B.next_bid(lot)
        leading = lot.current_bidder_id == character.id
        is_seller = lot.seller_id == character.id
        buyout_price = lot.price or 0
        from engine.currency import currency_str, total_in_bronze

        purse = currency_str(character)
        can_pay = total_in_bronze(character) >= required

    lines = [f"🔨 <b>{name}</b>", f"🆔 <code>{uid}</code>", "",
             B.lot_line(lot), f"👤 Продавец: {lot.seller_name or 'скупщик'}",
             f"📈 Ставок: {lot.bid_count or 0}", "",
             f"💰 У тебя: {purse}"]
    if leading:
        lines.append("✅ <i>Сейчас лидируешь ты.</i>")
    if buyout_price:
        lines.append(f"⚡️ Выкупить сразу: <b>{buyout_price}</b>🟤")

    builder = InlineKeyboardBuilder()
    if not is_seller and not leading:
        if can_pay:
            builder.button(text=f"🔨 Ставка {required}🟤",
                           callback_data=f"bid_place:{lot.id}:{required}")
            # Шаг вверх: удобно перебить с запасом, не считая в уме.
            bigger = required + B.min_step(required) * 2
            if total_in_bronze(character) >= bigger:
                builder.button(text=f"🔨 Ставка {bigger}🟤",
                               callback_data=f"bid_place:{lot.id}:{bigger}")
        else:
            lines.append(f"<i>Не хватает {required - total_in_bronze(character)}🟤 "
                         f"на минимальную ставку.</i>")
        if buyout_price and total_in_bronze(character) >= buyout_price:
            builder.button(text=f"⚡️ Выкупить за {buyout_price}🟤",
                           callback_data=f"bid_buyout:{lot.id}")
    if is_seller and not lot.current_bid:
        builder.button(text="🚫 Снять с торгов",
                       callback_data=f"bid_cancel:{lot.id}")
    builder.button(text="🔄 Обновить", callback_data=f"bid_lot:{lot.id}")
    builder.button(text="◀️ К торгам", callback_data="bids_menu")
    builder.adjust(1)

    await safe_edit_text(callback, "\n".join(lines),
                         reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("bid_place:"))
async def bid_place(callback: CallbackQuery):
    """Сделать ставку."""
    _, raw_id, raw_amount = callback.data.split(":")
    lot_id, amount = int(raw_id), int(raw_amount)

    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        lot = await session.get(AuctionLot, lot_id)
        if lot is None or character is None:
            await callback.answer("Лот не найден.", show_alert=True)
            return
        outcome = await B.place_bid(session, character, lot, amount)
        await session.commit()

    if not outcome["ok"]:
        await callback.answer(outcome["reason"], show_alert=True)
        callback.data = f"bid_lot:{lot_id}"
        await bid_lot(callback)
        return

    if outcome.get("outbid_character_id"):
        await _notify(outcome["outbid_character_id"],
                      f"⚔️ <b>Твою ставку перебили.</b>\n\n"
                      f"Возвращено {outcome['refunded']}🟤. "
                      f"Новая ставка — {outcome['amount']}🟤.")

    tail = " Торги продлены." if outcome.get("extended") else ""
    await callback.answer(f"Ставка {outcome['amount']}🟤 принята.{tail}")
    callback.data = f"bid_lot:{lot_id}"
    await bid_lot(callback)


@router.callback_query(F.data.startswith("bid_buyout:"))
async def bid_buyout(callback: CallbackQuery):
    """Выкупить лот, не дожидаясь молотка."""
    lot_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        lot = await session.get(AuctionLot, lot_id)
        if lot is None or character is None:
            await callback.answer("Лот не найден.", show_alert=True)
            return
        seller_id, refunded_to = lot.seller_id, lot.current_bidder_id
        refunded = lot.current_bid or 0
        outcome = await B.buyout(session, character, lot)
        await session.commit()
        name = ""
        if outcome.get("ok"):
            name = outcome["instance"].display_name(outcome["item"])

    if not outcome.get("ok"):
        await callback.answer(outcome["reason"], show_alert=True)
        return

    if refunded_to and refunded_to != character.id:
        await _notify(refunded_to,
                      f"⚡️ <b>Лот выкупили.</b> Твоя ставка {refunded}🟤 "
                      f"возвращена.")
    await _notify(seller_id,
                  f"💰 <b>Твой лот выкупили</b> за {outcome['amount']}🟤. "
                  f"На руки: {outcome['payout']}🟤.")

    await safe_edit_text(
        callback,
        f"⚡️ <b>Выкуплено</b>\n\n{name}\n\n"
        f"Списано: <b>{outcome['amount']}</b>🟤\n"
        f"<i>Вещь легла в сумку вместе со своей историей.</i>",
        reply_markup=_back_keyboard(), parse_mode="HTML")


@router.callback_query(F.data.startswith("bid_cancel:"))
async def bid_cancel(callback: CallbackQuery):
    """Снять свой лот, пока никто не поставил."""
    lot_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        lot = await session.get(AuctionLot, lot_id)
        if lot is None or character is None:
            await callback.answer("Лот не найден.", show_alert=True)
            return
        outcome = await B.cancel_bid_lot(session, character, lot)
        await session.commit()

    if not outcome["ok"]:
        await callback.answer(outcome["reason"], show_alert=True)
        return
    await callback.answer("Лот снят, вещь вернулась в сумку.")
    callback.data = "bids_menu"
    await bids_menu(callback)


@router.callback_query(F.data.startswith("bid_sell:"))
async def bid_sell(callback: CallbackQuery):
    """Выбор вещи для торгов."""
    page = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if character is None:
            await callback.answer("Сначала создай героя.", show_alert=True)
            return
        from core import auction as core_auction

        items = await core_auction.sellable_items(session, character.id)
        rows = []
        for inv in items[page * PER_PAGE:(page + 1) * PER_PAGE]:
            low, high = core_auction.price_bounds(inv.instance, inv.item)
            start = max(low, int(core_auction.suggested_price(
                inv.instance, inv.item) * 0.6))
            rows.append((inv.id, inv.instance.display_name(inv.item), start))

    builder = InlineKeyboardBuilder()
    for inv_id, name, start in rows:
        builder.button(text=f"{name} · старт {start}🟤",
                       callback_data=f"bid_list:{inv_id}:{start}")
    if len(items) > (page + 1) * PER_PAGE:
        builder.button(text="▶️ Ещё", callback_data=f"bid_sell:{page + 1}")
    builder.button(text="◀️ К торгам", callback_data="bids_menu")
    builder.adjust(1)

    text = ("📢 <b>Выставить с молотка</b>\n\n"
            "<i>Стартовая цена берётся ниже рыночной: с молотка выгодно "
            "начинать дёшево — цену поднимут сами.</i>\n\n"
            f"<i>Торги идут {int(B.BID_LIFETIME.total_seconds() // 3600)} ч. "
            f"Ставка в последние {int(B.ANTISNIPE_WINDOW.total_seconds() // 60)} "
            f"мин продлевает их.</i>")
    if not rows:
        text = ("📢 <b>Выставить с молотка</b>\n\n"
                "<i>Именных вещей в сумке нет. С молотка уходят только "
                "предметы со своим ID.</i>")

    await safe_edit_text(callback, text, reply_markup=builder.as_markup(),
                         parse_mode="HTML")


@router.callback_query(F.data.startswith("bid_list:"))
async def bid_list(callback: CallbackQuery):
    """Выставить вещь с выбранной стартовой ценой."""
    _, raw_inv, raw_start = callback.data.split(":")
    inv_id, start = int(raw_inv), int(raw_start)

    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        inv = (await session.execute(
            select(InventoryItem).where(InventoryItem.id == inv_id)
            .options(selectinload(InventoryItem.item),
                     selectinload(InventoryItem.instance))
        )).scalar_one_or_none()
        if inv is None or character is None or inv.character_id != character.id:
            await callback.answer("Предмет не найден.", show_alert=True)
            return
        name = inv.instance.display_name(inv.item) if inv.instance else "вещь"
        # Выкуп — вчетверо от старта: даёт нетерпеливым выход, но не
        # обесценивает торги.
        outcome = await B.list_bid_lot(session, character, inv,
                                       start_bid=start, buyout=start * 4)
        await session.commit()

    if not outcome["ok"]:
        await callback.answer(outcome["reason"], show_alert=True)
        return

    hours = int(B.BID_LIFETIME.total_seconds() // 3600)
    await safe_edit_text(
        callback,
        f"🔨 <b>Выставлено с молотка</b>\n\n{name}\n\n"
        f"Стартовая ставка: <b>{start}</b>🟤\n"
        f"Выкуп сразу: <b>{start * 4}</b>🟤\n"
        f"Торги идут <b>{hours} ч</b>.\n\n"
        f"<i>Когда кто-то поставит, придёт весть.</i>",
        reply_markup=_back_keyboard(), parse_mode="HTML")
