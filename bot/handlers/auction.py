"""Аукцион: витрина, выставление лотов, покупка и скупщик-NPC."""
from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core import auction, history
from core.database import async_session
from core.models import AuctionLot, Character, InventoryItem, User
from bot.keyboards.inline import (
    auction_browse_keyboard, auction_lot_keyboard, auction_menu_keyboard,
    auction_my_lots_keyboard, auction_price_keyboard, auction_sell_list_keyboard,
    main_menu_keyboard,
)
from bot.utils.photos import send_or_edit_photo

router = Router()


async def _character(session, telegram_id: int):
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        return None
    result = await session.execute(
        select(Character).where(Character.user_id == user.id)
    )
    return result.scalar_one_or_none()


@router.callback_query(F.data == "auction_menu")
async def auction_menu(callback: CallbackQuery):
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        # Просроченные лоты возвращаются владельцам при каждом заходе
        await auction.sweep_expired(session)
        await session.commit()

        lots = await auction.active_lots(session)
        mine = await auction.my_lots(session, character.id)
        gold = character.gold

    await callback.message.edit_text(
        "⚖️ <b>Аукцион Теневых Земель</b>\n\n"
        "<i>Скупщик Молчун не поднимает глаз от гроссбуха.</i>\n\n"
        "— Выставляй, если не спешишь: покупатель найдётся. Или продай мне "
        "сразу — дешевле, зато сейчас. Всё записано, вон, гляди.\n\n"
        f"🛒 Лотов на витрине: <b>{len(lots)}</b>\n"
        f"📋 Твоих лотов: <b>{len(mine)}</b> из {auction.MAX_ACTIVE_LOTS}\n"
        f"🪙 У тебя золота: <b>{gold}</b>\n\n"
        f"<i>Комиссия аукциона — {int(auction.COMMISSION * 100)} %. "
        f"Непроданный лот вернётся через сутки.</i>",
        reply_markup=auction_menu_keyboard(len(mine)),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("auction_browse:"))
async def auction_browse(callback: CallbackQuery):
    page = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        lots = await auction.active_lots(session)

    if not lots:
        await callback.answer("Витрина пуста. Загляни позже.", show_alert=True)
        return

    await callback.message.edit_text(
        f"🛒 <b>Витрина аукциона</b>\n\n"
        f"Лотов: <b>{len(lots)}</b> | У тебя: <b>{character.gold}</b>🪙\n\n"
        "<i>Значок перед ценой — способ добычи вещи. "
        "🔁 значит, что она уже меняла хозяев.</i>",
        reply_markup=auction_browse_keyboard(lots, page),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("auction_lot:"))
async def auction_lot_view(callback: CallbackQuery):
    lot_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        result = await session.execute(
            select(AuctionLot)
            .where(AuctionLot.id == lot_id)
            .options(
                selectinload(AuctionLot.item),
                selectinload(AuctionLot.instance),
            )
        )
        lot = result.scalar_one_or_none()
        if lot is None or not character:
            await callback.answer("Лот не найден.", show_alert=True)
            return

        rows = await history.load(session, lot.instance_id)
        summary = await history.history_summary(session, lot.instance)

    inst, item = lot.instance, lot.item
    title = inst.display_name(item)
    if inst.is_one_of_a_kind:
        title = f"🌟 {title}"
    elif inst.is_festive:
        title = f"🎄 {title}"

    lines = [
        f"{item.icon} <b>{title}</b>",
        f"🆔 <code>{inst.tagged_uid()}</code>",
        f"{inst.badge()} <i>{inst.source_title()}</i>",
        f"⚖️ Качество: <b>{inst.quality}%</b>"
        + (f" | 🔨 +{inst.upgrade_level}" if inst.upgrade_level else ""),
        "",
    ]
    if summary:
        lines += [summary, ""]

    labels = {
        "bonus_strength": "💪", "bonus_agility": "🏃", "bonus_intelligence": "🧠",
        "bonus_endurance": "🛡", "bonus_luck": "🍀", "bonus_hp": "❤️",
        "bonus_mp": "💙", "bonus_damage": "⚔️", "bonus_defense": "🛡",
    }
    bonuses = [
        f"{label} +{value}"
        for field, label in labels.items()
        for value in [getattr(inst, field, 0)] if value
    ]
    if bonuses:
        lines += ["<b>Бонусы:</b> " + ", ".join(bonuses), ""]

    lines += [
        f"👤 Продавец: <b>{lot.seller_name or 'Скупщик'}</b>",
        f"💰 Цена: <b>{lot.price}</b>🪙 (у тебя {character.gold}🪙)",
    ]
    if item.level_requirement and item.level_requirement > 1:
        lines.append(f"⭐ Требуется уровень: {item.level_requirement}")

    if rows:
        lines += ["", "<b>📖 История предмета</b>", history.format_history(rows, 6)]

    is_mine = lot.seller_id == character.id
    can_buy = (
        not is_mine
        and character.gold >= lot.price
        and character.level >= (item.level_requirement or 1)
    )

    await send_or_edit_photo(
        callback,
        "\n".join(lines),
        reply_markup=auction_lot_keyboard(lot.id, can_buy, is_mine),
        image_url=item.image_url,
    )


@router.callback_query(F.data.startswith("auction_buy:"))
async def auction_buy(callback: CallbackQuery):
    lot_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        result = await session.execute(
            select(AuctionLot)
            .where(AuctionLot.id == lot_id)
            .options(selectinload(AuctionLot.item))
        )
        lot = result.scalar_one_or_none()
        if lot is None or not character:
            await callback.answer("Лот не найден.", show_alert=True)
            return

        seller_id = lot.seller_id
        seller_payout = 0
        outcome = await auction.buy_lot(session, character, lot)
        if outcome["ok"]:
            seller_payout = outcome["payout"]
        await session.commit()

        if outcome["ok"]:
            inst, item = outcome["instance"], outcome["item"]
            name = inst.display_name(item)
            uid = inst.tagged_uid()
            price = lot.price
            # Продавцу — весточка о продаже
            seller_tg = None
            if seller_id and not lot.is_npc_lot:
                seller = await session.get(Character, seller_id)
                if seller is not None:
                    seller_user = await session.get(User, seller.user_id)
                    seller_tg = seller_user.telegram_id if seller_user else None

    if not outcome["ok"]:
        await callback.answer(outcome["reason"], show_alert=True)
        return

    if seller_tg:
        try:
            from bot.runner import bot_runner
            if bot_runner.is_running() and bot_runner.bot:
                await bot_runner.bot.send_message(
                    chat_id=seller_tg,
                    text=(
                        f"💰 <b>Твой лот продан!</b>\n\n"
                        f"{name} ушёл за {price}🪙.\n"
                        f"На руки: <b>{seller_payout}</b>🪙 "
                        f"(комиссия {int(auction.COMMISSION * 100)} %)."
                    ),
                    parse_mode="HTML",
                )
        except Exception:
            pass

    await callback.message.edit_text(
        f"✅ <b>Покупка состоялась</b>\n\n"
        f"{name}\n"
        f"🆔 <code>{uid}</code>\n\n"
        f"Списано: <b>{price}</b>🪙\n"
        f"Осталось: <b>{character.gold}</b>🪙\n\n"
        f"<i>Вещь легла в сумку вместе со своей историей.</i>",
        reply_markup=auction_menu_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("auction_my_items:"))
async def auction_my_items(callback: CallbackQuery):
    page = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        items = await auction.sellable_items(session, character.id)

    if not items:
        await callback.answer(
            "Нечего выставлять: на аукцион идут только именные вещи, "
            "и снятые с себя.",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        "📢 <b>Что выставим?</b>\n\n"
        "Ресурсы и расходники аукцион не принимает — только вещи "
        "со своим ID.\n\n"
        "<i>Надетое сначала сними.</i>",
        reply_markup=auction_sell_list_keyboard(items, page),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("auction_sell:"))
async def auction_sell(callback: CallbackQuery):
    """Экран выбора цены для конкретной вещи."""
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.id == inv_id)
            .options(
                selectinload(InventoryItem.item),
                selectinload(InventoryItem.instance),
            )
        )
        inv = result.scalar_one_or_none()
        if inv is None or not character or inv.character_id != character.id:
            await callback.answer("Предмет не найден.", show_alert=True)
            return
        if inv.instance is None:
            await callback.answer(
                "Ресурсы и расходники на аукцион не принимают.", show_alert=True
            )
            return
        if inv.is_equipped:
            await callback.answer("Сначала сними предмет.", show_alert=True)
            return

        hint = auction.suggested_price(inv.instance, inv.item)
        npc_price = await auction.npc_quote(session, inv)
        low, high = auction.price_bounds(inv.instance, inv.item)
        name = inv.display_name()
        uid = inv.instance.tagged_uid()
        image = inv.item.image_url

    prices = [
        ("💸 Быстро", max(low, int(hint * 0.7))),
        ("⚖️ По рынку", hint),
        ("💎 Дорого", int(hint * 1.5)),
        ("🤑 Очень дорого", min(high, int(hint * 2.5))),
    ]

    await send_or_edit_photo(
        callback,
        f"📢 <b>{name}</b>\n"
        f"🆔 <code>{uid}</code>\n\n"
        f"Оценка аукциона: <b>{hint}</b>🪙\n"
        f"Допустимая цена: от {low}🪙 до {high}🪙\n\n"
        f"Выбери, за сколько выставить. Комиссия — "
        f"{int(auction.COMMISSION * 100)} % с продажи.\n"
        f"Не купят за сутки — вещь вернётся в сумку.",
        reply_markup=auction_price_keyboard(inv_id, prices, npc_price),
        image_url=image,
    )


@router.callback_query(F.data.startswith("auction_list:"))
async def auction_list(callback: CallbackQuery):
    _, inv_id_s, price_s = callback.data.split(":")
    inv_id, price = int(inv_id_s), int(price_s)

    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.id == inv_id)
            .options(
                selectinload(InventoryItem.item),
                selectinload(InventoryItem.instance),
            )
        )
        inv = result.scalar_one_or_none()
        if inv is None or not character or inv.character_id != character.id:
            await callback.answer("Предмет не найден.", show_alert=True)
            return

        name = inv.display_name()
        outcome = await auction.list_lot(session, character, inv, price)
        await session.commit()
        mine = await auction.my_lots(session, character.id)

    if not outcome["ok"]:
        await callback.answer(outcome["reason"], show_alert=True)
        return

    await callback.message.edit_text(
        f"📢 <b>Лот выставлен</b>\n\n"
        f"{name} — <b>{price}</b>🪙\n\n"
        f"<i>Молчун вписывает строку в гроссбух. "
        f"Если не купят за сутки, вещь вернётся к тебе.</i>",
        reply_markup=auction_menu_keyboard(len(mine)),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("auction_npc_sell:"))
async def auction_npc_sell(callback: CallbackQuery):
    """Мгновенная продажа скупщику — дешевле, зато без ожидания."""
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.id == inv_id)
            .options(
                selectinload(InventoryItem.item),
                selectinload(InventoryItem.instance),
            )
        )
        inv = result.scalar_one_or_none()
        if inv is None or not character or inv.character_id != character.id:
            await callback.answer("Предмет не найден.", show_alert=True)
            return

        name = inv.display_name()
        outcome = await auction.npc_buy(session, character, inv)
        await session.commit()
        gold = character.gold

    if not outcome["ok"]:
        await callback.answer(outcome["reason"], show_alert=True)
        return

    await callback.message.edit_text(
        f"⚡ <b>Продано скупщику</b>\n\n"
        f"{name} → <b>{outcome['price']}</b>🪙\n"
        f"Теперь у тебя: <b>{gold}</b>🪙\n\n"
        f"<i>Молчун сдувает пыль с вещи и ставит её на витрину. "
        f"История предмета остаётся с ним.</i>",
        reply_markup=auction_menu_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "auction_my_lots")
async def auction_my_lots(callback: CallbackQuery):
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        lots = await auction.my_lots(session, character.id)

    if not lots:
        await callback.answer("У тебя нет активных лотов.", show_alert=True)
        return

    lines = ["📋 <b>Твои лоты</b>\n"]
    for lot in lots:
        name = lot.instance.display_name(lot.item) if lot.instance else "?"
        left = ""
        if lot.expires_at:
            from datetime import datetime
            hours = int((lot.expires_at - datetime.utcnow()).total_seconds() // 3600)
            left = f" · осталось ~{max(0, hours)}ч"
        lines.append(f"• {name} — <b>{lot.price}</b>🪙{left}")
    lines.append("\n<i>Нажми на лот, чтобы снять его с продажи.</i>")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=auction_my_lots_keyboard(lots),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("auction_cancel:"))
async def auction_cancel(callback: CallbackQuery):
    lot_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        lot = await session.get(AuctionLot, lot_id)
        if lot is None or not character:
            await callback.answer("Лот не найден.", show_alert=True)
            return

        outcome = await auction.cancel_lot(session, character, lot)
        await session.commit()
        mine = await auction.my_lots(session, character.id)

    if not outcome["ok"]:
        await callback.answer(outcome["reason"], show_alert=True)
        return

    await callback.message.edit_text(
        "↩️ <b>Лот снят с продажи</b>\n\nВещь вернулась в сумку.",
        reply_markup=auction_menu_keyboard(len(mine)),
        parse_mode="HTML",
    )
