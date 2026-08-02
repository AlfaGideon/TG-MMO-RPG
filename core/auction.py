"""Аукцион: игроки продают друг другу уникальные экземпляры предметов.

Работает по принципу «купить сразу»: продавец назначает цену, покупатель
жмёт кнопку и вещь меняет владельца. Каждая сделка пишется в летопись
предмета (`core/history.py`), поэтому купленная вещь приходит «с
историей» — видно, из кого её выбили и через сколько рук она прошла.

Скупщик-NPC подстраховывает рынок: он выкупает залежавшиеся лоты по
сниженной цене и перевыставляет их, чтобы вещи не пропадали.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import selectinload

from core import history
from core.enums import AuctionStatus, ItemSource
from core.loot import instance_price
from core.models import (
    AuctionLot, Character, InventoryItem, Item, ItemInstance,
)

# Сколько лот висит, прежде чем вернуться продавцу
LOT_LIFETIME = timedelta(hours=24)

# Комиссия аукциона с продажи (доля)
COMMISSION = 0.05

# Скупщик даёт меньше рынка, зато берёт что угодно и сразу
NPC_BUY_FACTOR = 0.55
NPC_SELL_MARKUP = 1.35

# Границы цены относительно оценочной стоимости — защита от опечаток
MIN_PRICE_FACTOR = 0.2
MAX_PRICE_FACTOR = 20.0

MAX_ACTIVE_LOTS = 5


def _now():
    # aware-время под timestamptz-колонки: на Postgres так корректно,
    # SQLite при записи отбрасывает tz — сравнения остаются согласованными.
    return datetime.now(timezone.utc)


async def _claim_lot(session, lot: AuctionLot, new_status: str) -> bool:
    """Атомарно перевести лот из ACTIVE в `new_status`.

    Обычное «прочитал статус → проверил → записал» даёт гонку: два
    покупателя одновременно видели ACTIVE, оба списывали золото и оба
    получали одну и ту же вещь (см. отсутствие уникальности у
    InventoryItem.instance_id). Условный UPDATE отщёлкивает статус ровно
    один раз: у проигравшего гонку rowcount == 0.
    """
    res = await session.execute(
        update(AuctionLot)
        .where(AuctionLot.id == lot.id)
        .where(AuctionLot.status == AuctionStatus.ACTIVE.value)
        .values(status=new_status)
    )
    if res.rowcount != 1:
        return False
    lot.status = new_status
    return True


def suggested_price(instance: ItemInstance, item: Item) -> int:
    """Ориентир цены: базовая стоимость с учётом качества и заточки."""
    base = instance_price(instance, item.price or 10)
    # За «намоленность» — вещь с историей ценится чуть выше
    base = int(base * (1 + 0.05 * min(5, instance.trade_count or 0)))
    if instance.is_one_of_a_kind:
        base *= 5
    elif instance.is_festive:
        base = int(base * 1.5)
    return max(1, base)


def price_bounds(instance: ItemInstance, item: Item) -> tuple[int, int]:
    hint = suggested_price(instance, item)
    return max(1, int(hint * MIN_PRICE_FACTOR)), int(hint * MAX_PRICE_FACTOR)


async def active_lots(session, exclude_seller_id: int | None = None, limit: int = 50):
    """Лоты, доступные к покупке прямо сейчас."""
    query = (
        select(AuctionLot)
        .options(
            selectinload(AuctionLot.item),
            selectinload(AuctionLot.instance),
        )
        .where(AuctionLot.status == AuctionStatus.ACTIVE.value)
        .order_by(AuctionLot.created_at.desc())
        .limit(limit)
    )
    if exclude_seller_id is not None:
        # SQL NULL != value is UNKNOWN, so include NPC lots (seller_id NULL)
        # explicitly when building a public/buyable showcase.
        query = query.where(
            or_(AuctionLot.seller_id.is_(None), AuctionLot.seller_id != exclude_seller_id)
        )
    result = await session.execute(query)
    return result.scalars().all()


async def my_lots(session, character_id: int):
    result = await session.execute(
        select(AuctionLot)
        .options(selectinload(AuctionLot.item), selectinload(AuctionLot.instance))
        .where(AuctionLot.seller_id == character_id)
        .where(AuctionLot.status == AuctionStatus.ACTIVE.value)
        .order_by(AuctionLot.created_at.desc())
    )
    return result.scalars().all()


async def sellable_items(session, character_id: int):
    """Что игрок может выставить: уникальные экземпляры, кроме надетого."""
    result = await session.execute(
        select(InventoryItem)
        .options(
            selectinload(InventoryItem.item),
            selectinload(InventoryItem.instance),
        )
        .where(InventoryItem.character_id == character_id)
        .where(InventoryItem.instance_id.isnot(None))
        .where(InventoryItem.is_equipped == False)  # noqa: E712
        .order_by(InventoryItem.id)
    )
    rows = result.scalars().all()
    return [r for r in rows if r.item and r.item.is_sellable]


async def list_lot(session, character, inv_item: InventoryItem, price: int) -> dict:
    """Выставляет предмет на аукцион. Вещь уходит из сумки в витрину."""
    instance = inv_item.instance
    item = inv_item.item
    if instance is None:
        return {"ok": False, "reason": "Ресурсы и расходники на аукцион не принимают."}
    if inv_item.is_equipped:
        return {"ok": False, "reason": "Сначала сними предмет."}
    if item is not None and not item.is_sellable:
        return {"ok": False, "reason": "Этот предмет нельзя продавать."}

    running = await session.scalar(
        select(func.count(AuctionLot.id))
        .where(AuctionLot.seller_id == character.id)
        .where(AuctionLot.status == AuctionStatus.ACTIVE.value)
    ) or 0
    if running >= MAX_ACTIVE_LOTS:
        return {
            "ok": False,
            "reason": f"Больше {MAX_ACTIVE_LOTS} лотов сразу выставить нельзя.",
        }

    low, high = price_bounds(instance, item)
    if price < low or price > high:
        return {
            "ok": False,
            "reason": f"Цена должна быть от {low}🟤 до {high}🟤.",
        }

    lot = AuctionLot(
        instance_id=instance.id, item_id=item.id,
        seller_id=character.id, seller_name=character.name or "",
        price=price, status=AuctionStatus.ACTIVE.value,
        expires_at=_now() + LOT_LIFETIME,
    )
    session.add(lot)
    # Предмет физически покидает сумку, пока висит на витрине
    await session.delete(inv_item)
    instance.owner_character_id = None
    await history.record(
        session, instance, "listed", character,
        detail="выставлен на аукцион", price=price,
    )
    await session.flush()
    return {"ok": True, "lot": lot}


async def cancel_lot(session, character, lot: AuctionLot) -> dict:
    """Снимает свой лот с витрины и возвращает вещь в сумку."""
    if lot.seller_id != character.id:
        return {"ok": False, "reason": "Это не твой лот."}
    if lot.status != AuctionStatus.ACTIVE.value:
        return {"ok": False, "reason": "Лот уже неактивен."}

    # Атомарный захват: параллельный sweep/double-click не вернёт вещь дважды
    if not await _claim_lot(session, lot, AuctionStatus.CANCELLED.value):
        return {"ok": False, "reason": "Лот уже неактивен."}
    await _return_to_owner(session, lot, character, event="unlisted")
    await session.flush()
    return {"ok": True}


async def _return_to_owner(session, lot: AuctionLot, character, event: str):
    instance = await session.get(ItemInstance, lot.instance_id)
    if instance is None:
        return
    instance.owner_character_id = character.id if character else lot.seller_id
    session.add(InventoryItem(
        character_id=instance.owner_character_id,
        item_id=lot.item_id, instance_id=instance.id, quantity=1,
    ))
    await history.record(session, instance, event, character, detail="вернулся к владельцу")


async def buy_lot(session, buyer: Character, lot: AuctionLot) -> dict:
    """Покупка лота. Вещь меняет владельца и обрастает историей."""
    if lot.status != AuctionStatus.ACTIVE.value:
        return {"ok": False, "reason": "Лот уже продан или снят."}
    if lot.seller_id == buyer.id:
        return {"ok": False, "reason": "Нельзя купить собственный лот."}
    from engine.currency import total_in_bronze, deduct_currency, add_currency
    if total_in_bronze(buyer) < lot.price:
        return {"ok": False, "reason": f"Не хватает {lot.price - total_in_bronze(buyer)}🟤."}

    instance = await session.get(ItemInstance, lot.instance_id)
    item = await session.get(Item, lot.item_id)
    if instance is None or item is None:
        lot.status = AuctionStatus.CANCELLED.value
        return {"ok": False, "reason": "Предмет потерялся — лот отменён."}

    if buyer.level < (item.level_requirement or 1):
        return {
            "ok": False,
            "reason": f"Нужен {item.level_requirement} уровень, чтобы владеть этим.",
        }

    # Атомарный захват лота: только один покупатель проходит дальше,
    # второй получит отказ — денег у него не спишется и дубля вещи не будет.
    if not await _claim_lot(session, lot, AuctionStatus.SOLD.value):
        return {"ok": False, "reason": "Лот уже продан или снят."}

    deduct_currency(buyer, lot.price)

    # Продавцу — деньги за вычетом комиссии
    payout = max(1, int(lot.price * (1 - COMMISSION)))
    if lot.seller_id and not lot.is_npc_lot:
        seller = await session.get(Character, lot.seller_id)
        if seller is not None:
            add_currency(seller, bronze=payout)

    lot.status = AuctionStatus.SOLD.value
    lot.buyer_id = buyer.id
    lot.sold_at = _now()

    instance.owner_character_id = buyer.id
    instance.trade_count = (instance.trade_count or 0) + 1
    # Предмет, прошедший через аукцион, помечается как торгованный
    if instance.source not in (ItemSource.UNIQUE.value, ItemSource.FESTIVE.value):
        instance.source = ItemSource.AUCTION.value

    session.add(InventoryItem(
        character_id=buyer.id, item_id=item.id,
        instance_id=instance.id, quantity=1,
    ))
    await history.record(
        session, instance, "sold", buyer,
        detail=f"куплен у {lot.seller_name or 'скупщика'}", price=lot.price,
    )
    await session.flush()
    return {"ok": True, "lot": lot, "instance": instance, "item": item,
            "payout": payout}


async def sweep_expired(session) -> list[AuctionLot]:
    """Возвращает просроченные лоты продавцам. Зовётся фоновой задачей."""
    result = await session.execute(
        select(AuctionLot)
        .where(AuctionLot.status == AuctionStatus.ACTIVE.value)
        .where(AuctionLot.expires_at.isnot(None))
        .where(AuctionLot.expires_at < _now())
    )
    expired = result.scalars().all()
    claimed = []
    for lot in expired:
        # Гонка со снятием/покупкой: лот успели продать или снять — пропускаем
        if not await _claim_lot(session, lot, AuctionStatus.EXPIRED.value):
            continue
        claimed.append(lot)
        if lot.is_npc_lot or not lot.seller_id:
            # Лот скупщика просто снимается с витрины
            continue
        seller = await session.get(Character, lot.seller_id)
        await _return_to_owner(session, lot, seller, event="expired")
    return claimed


# ── Скупщик-NPC ─────────────────────────────────────────────

async def npc_quote(session, inv_item: InventoryItem) -> int:
    """Сколько скупщик даст за вещь прямо сейчас, без ожидания покупателя."""
    if inv_item.instance is None or inv_item.item is None:
        return 0
    return max(1, int(suggested_price(inv_item.instance, inv_item.item) * NPC_BUY_FACTOR))


async def npc_buy(session, character, inv_item: InventoryItem) -> dict:
    """Скупщик мгновенно выкупает вещь и перевыставляет её на витрину.

    Игрок получает деньги сразу, а предмет не исчезает из мира: он
    возвращается на аукцион по повышенной цене и сохраняет свою историю.
    """
    instance = inv_item.instance
    item = inv_item.item
    if instance is None:
        return {"ok": False, "reason": "Скупщик берёт только именные вещи."}
    if inv_item.is_equipped:
        return {"ok": False, "reason": "Сначала сними предмет."}
    if item is not None and not item.is_sellable:
        return {"ok": False, "reason": "Этот предмет нельзя продавать."}

    price = await npc_quote(session, inv_item)
    from engine.currency import add_currency
    add_currency(character, bronze=price)

    await session.delete(inv_item)
    instance.owner_character_id = None
    instance.trade_count = (instance.trade_count or 0) + 1
    await history.record(
        session, instance, "sold", character,
        detail="выкуплен скупщиком", price=price,
    )

    resale = max(price + 1, int(price * NPC_SELL_MARKUP))
    lot = AuctionLot(
        instance_id=instance.id, item_id=instance.item_id,
        seller_id=None, seller_name="Скупщик Молчун",
        price=resale, status=AuctionStatus.ACTIVE.value,
        is_npc_lot=True, expires_at=_now() + LOT_LIFETIME * 3,
    )
    session.add(lot)
    await history.record(
        session, instance, "listed", None,
        detail="выставлен скупщиком", price=resale,
    )
    await session.flush()
    return {"ok": True, "price": price, "lot": lot}
