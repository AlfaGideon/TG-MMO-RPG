"""Торги со ставками: лот уходит тому, кто поднял цену последним.

Раньше здесь была заглушка — одна константа, которую не читала ни одна
строка кода (IDEAS-100.md, № 59). Теперь это рабочая механика поверх той
же таблицы `AuctionLot`, что и обычный аукцион: отдельная сущность не
заводилась намеренно, иначе у вещи оказалось бы два разных пути продажи
и два места, где её можно потерять.

**Как отличается лот с молотка.** У него `start_bid > 0`. Обычный лот
(`start_bid == 0`) ведёт себя как прежде: фиксированная цена, кнопка
«Купить». У лота с торгами цена растёт, а `price` работает как «выкупить
сразу» — если продавец её назначил.

**Где лежат деньги ставки.** Списываются сразу, при ставке. Альтернатива
(«списать в конце у победителя») ломается о простое: игрок может успеть
потратить золото до закрытия торгов, и лот достанется тому, кто платить
нечем. Поэтому ставка — это резерв: деньги уходят из кошелька немедленно,
а перебитому лидеру возвращаются в тот же момент, когда его перебили.

**Гонка при одновременных ставках** решена тем же приёмом, что покупка
лота в `core/auction.py` (`_claim_lot`): условный UPDATE, который проходит
ровно один раз. Здесь условие сильнее — «обнови, только если текущая
ставка всё ещё та, которую я видел». Проигравший гонку получает отказ и
свои деньги обратно не теряет, потому что списание идёт после успешного
UPDATE, а не до него.

**Продление таймера (антиснайпинг).** Ставка в последние `ANTISNIPE_WINDOW`
продлевает торги: иначе выигрывает не тот, кто больше даёт, а тот, у кого
лучше пинг в последнюю секунду.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update

from core import history
from core.enums import AuctionStatus, ItemSource
from core.models import (AuctionLot, Character, InventoryItem, Item,
                         ItemInstance)

logger = logging.getLogger(__name__)

# Шаг ставки: не меньше 5 % от текущей цены и не меньше MIN_STEP бронзы.
# Без шага торги превращаются в перестрелку по +1🟤 на сотню сообщений.
STEP_PCT = 0.05
MIN_STEP = 5

# Сколько живут торги по умолчанию и на сколько продлеваются от снайпинга.
BID_LIFETIME = timedelta(hours=12)
ANTISNIPE_WINDOW = timedelta(minutes=5)
ANTISNIPE_EXTEND = timedelta(minutes=5)

# Комиссия дома с молотка — та же, что у обычной продажи.
from core.auction import COMMISSION, MAX_ACTIVE_LOTS, price_bounds  # noqa: E402


def _now():
    return datetime.now(timezone.utc)


def _aware(value):
    """Время из БД в aware-виде: SQLite отдаёт naive, Postgres — aware."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def is_bid_lot(lot: AuctionLot) -> bool:
    """Лот с молотка? Обычные лоты этот модуль не трогает."""
    return bool(lot is not None and (lot.start_bid or 0) > 0)


def min_step(current: int) -> int:
    """Минимальный шаг для текущей цены."""
    return max(MIN_STEP, int(current * STEP_PCT))


def next_bid(lot: AuctionLot) -> int:
    """Сколько нужно поставить, чтобы перебить лидера.

    Пока ставок нет, стартовая цена принимается как есть — иначе первый
    участник платил бы больше объявленного старта.
    """
    if not is_bid_lot(lot):
        return 0
    current = lot.current_bid or 0
    if current <= 0:
        return lot.start_bid
    return current + min_step(current)


def time_left(lot: AuctionLot):
    """Сколько осталось до удара молотка (timedelta) или None."""
    expires = _aware(lot.expires_at)
    if expires is None:
        return None
    return expires - _now()


def lot_line(lot: AuctionLot) -> str:
    """Строка состояния торгов для экранов бота и панели."""
    if not is_bid_lot(lot):
        return ""
    if lot.current_bid:
        head = (f"🔨 Ставка: <b>{lot.current_bid}</b>🟤 "
                f"({lot.current_bidder_name or 'аноним'})")
    else:
        head = f"🔨 Стартовая цена: <b>{lot.start_bid}</b>🟤 — ставок нет"
    left = time_left(lot)
    if left is not None and left.total_seconds() > 0:
        minutes = int(left.total_seconds() // 60)
        head += (f" · осталось {minutes // 60} ч {minutes % 60} мин"
                 if minutes >= 60 else f" · осталось {minutes} мин")
    return head


# ── выставление ─────────────────────────────────────────────

async def list_bid_lot(session, character, inv_item: InventoryItem,
                       start_bid: int, buyout: int = 0,
                       hours: float | None = None) -> dict:
    """Выставить вещь на торги.

    Проверки те же, что у обычного лота (`core/auction.list_lot`), плюс
    правило выкупа: цена «купить сразу» обязана быть выше стартовой ставки,
    иначе торги бессмысленны — выгоднее сразу выкупить.
    """
    instance = inv_item.instance
    item = inv_item.item
    if instance is None:
        return {"ok": False, "reason": "С молотка уходят только именные вещи."}
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
        return {"ok": False,
                "reason": f"Больше {MAX_ACTIVE_LOTS} лотов сразу нельзя."}

    low, high = price_bounds(instance, item)
    if start_bid < low or start_bid > high:
        return {"ok": False,
                "reason": f"Стартовая ставка — от {low}🟤 до {high}🟤."}
    if buyout and buyout <= start_bid:
        return {"ok": False,
                "reason": "Цена выкупа должна быть выше стартовой ставки."}

    lifetime = BID_LIFETIME if hours is None else timedelta(hours=hours)
    lot = AuctionLot(
        instance_id=instance.id, item_id=item.id,
        seller_id=character.id, seller_name=character.name or "",
        price=int(buyout or 0), status=AuctionStatus.ACTIVE.value,
        start_bid=int(start_bid), current_bid=0, bid_count=0,
        expires_at=_now() + lifetime,
    )
    session.add(lot)
    # Вещь физически покидает сумку, как и у обычного лота.
    await session.delete(inv_item)
    instance.owner_character_id = None
    await history.record(session, instance, "listed", character,
                         detail="выставлен на торги", price=start_bid)
    await session.flush()
    return {"ok": True, "lot": lot}


# ── ставка ──────────────────────────────────────────────────

async def place_bid(session, bidder: Character, lot: AuctionLot,
                    amount: int) -> dict:
    """Поднять ставку.

    Порядок операций важен и выбран так, чтобы деньги не пропадали:
      1. проверки без изменения состояния;
      2. атомарный UPDATE «перебей ровно ту ставку, которую я видел»;
      3. только после успеха — списание с нового лидера и возврат прежнему.

    Если шаг 2 не прошёл (кто-то успел раньше), у игрока ничего не списано.
    """
    from engine.currency import add_currency, deduct_currency, total_in_bronze

    if not is_bid_lot(lot):
        return {"ok": False, "reason": "Этот лот продаётся по фиксированной цене."}
    if lot.status != AuctionStatus.ACTIVE.value:
        return {"ok": False, "reason": "Торги уже закрыты."}
    if lot.seller_id == bidder.id:
        return {"ok": False, "reason": "Нельзя торговаться за собственный лот."}
    if lot.current_bidder_id == bidder.id:
        return {"ok": False, "reason": "Ты уже лидируешь в этих торгах."}

    left = time_left(lot)
    if left is not None and left.total_seconds() <= 0:
        return {"ok": False, "reason": "Время торгов вышло."}

    item = await session.get(Item, lot.item_id)
    if item is not None and bidder.level < (item.level_requirement or 1):
        return {"ok": False,
                "reason": f"Нужен {item.level_requirement} уровень для этой вещи."}

    required = next_bid(lot)
    amount = int(amount)
    if amount < required:
        return {"ok": False,
                "reason": f"Минимальная ставка — {required}🟤."}
    if total_in_bronze(bidder) < amount:
        return {"ok": False,
                "reason": f"Не хватает {amount - total_in_bronze(bidder)}🟤."}

    previous_id = lot.current_bidder_id
    previous_amount = lot.current_bid or 0
    # Значения читаем ДО UPDATE: после него ORM помечает объект устаревшим,
    # и обращение к полю потянуло бы ленивую загрузку прямо во flush
    # (MissingGreenlet в async-сессии).
    previous_count = lot.bid_count or 0

    # Антиснайпинг: ставка на последних минутах продлевает торги.
    new_expires = _aware(lot.expires_at)
    extended = False
    if new_expires is not None and (new_expires - _now()) <= ANTISNIPE_WINDOW:
        new_expires = _now() + ANTISNIPE_EXTEND
        extended = True

    # Условный UPDATE: проходит, только если ставка с момента чтения не
    # изменилась. Двое одновременных участников — один выигрывает, второй
    # получает отказ, не потеряв денег.
    res = await session.execute(
        update(AuctionLot)
        .where(AuctionLot.id == lot.id)
        .where(AuctionLot.status == AuctionStatus.ACTIVE.value)
        .where(func.coalesce(AuctionLot.current_bid, 0) == previous_amount)
        .values(current_bid=amount, current_bidder_id=bidder.id,
                current_bidder_name=bidder.name or "",
                bid_count=previous_count + 1,
                expires_at=new_expires)
        .execution_options(synchronize_session=False)
    )
    if res.rowcount != 1:
        return {"ok": False,
                "reason": "Кто-то опередил тебя — ставка выросла."}

    deduct_currency(bidder, amount)

    # Возврат прежнему лидеру: его деньги были в резерве, а не потрачены.
    refunded = 0
    if previous_id and previous_amount:
        previous = await session.get(Character, previous_id)
        if previous is not None:
            add_currency(previous, bronze=previous_amount)
            refunded = previous_amount

    # Синхронизируем объект в памяти с тем, что уже записано в БД.
    lot.current_bid = amount
    lot.current_bidder_id = bidder.id
    lot.current_bidder_name = bidder.name or ""
    lot.bid_count = previous_count + 1
    lot.expires_at = new_expires

    await session.flush()
    return {"ok": True, "amount": amount, "extended": extended,
            "outbid_character_id": previous_id, "refunded": refunded,
            "next_bid": next_bid(lot)}


async def buyout(session, buyer: Character, lot: AuctionLot) -> dict:
    """Выкупить лот с торгов сразу, не дожидаясь молотка."""
    from engine.currency import add_currency, deduct_currency, total_in_bronze

    if not is_bid_lot(lot):
        return {"ok": False, "reason": "Это не лот с торгами."}
    if not lot.price:
        return {"ok": False, "reason": "У этого лота нет цены выкупа."}
    if lot.status != AuctionStatus.ACTIVE.value:
        return {"ok": False, "reason": "Торги уже закрыты."}
    if lot.seller_id == buyer.id:
        return {"ok": False, "reason": "Нельзя выкупить собственный лот."}
    if total_in_bronze(buyer) < lot.price:
        return {"ok": False,
                "reason": f"Не хватает {lot.price - total_in_bronze(buyer)}🟤."}

    # Атомарный захват: параллельная ставка или второй выкуп не пройдут.
    res = await session.execute(
        update(AuctionLot)
        .where(AuctionLot.id == lot.id)
        .where(AuctionLot.status == AuctionStatus.ACTIVE.value)
        .values(status=AuctionStatus.SOLD.value)
        .execution_options(synchronize_session=False)
    )
    if res.rowcount != 1:
        return {"ok": False, "reason": "Лот уже ушёл."}
    lot.status = AuctionStatus.SOLD.value

    deduct_currency(buyer, lot.price)

    # Текущему лидеру возвращаем резерв: он проиграл, но не должен платить.
    if lot.current_bidder_id and lot.current_bid:
        loser = await session.get(Character, lot.current_bidder_id)
        if loser is not None:
            add_currency(loser, bronze=lot.current_bid)

    result = await _hand_over(session, lot, buyer, lot.price,
                              detail="выкуплен на торгах")
    result["outbid_character_id"] = lot.current_bidder_id
    return result


# ── закрытие торгов ─────────────────────────────────────────

async def _hand_over(session, lot: AuctionLot, winner: Character,
                     amount: int, detail: str) -> dict:
    """Передать вещь победителю и заплатить продавцу за вычетом комиссии."""
    from engine.currency import add_currency

    instance = await session.get(ItemInstance, lot.instance_id)
    item = await session.get(Item, lot.item_id)
    if instance is None or item is None:
        lot.status = AuctionStatus.CANCELLED.value
        return {"ok": False, "reason": "Предмет потерялся — лот отменён."}

    payout = max(1, int(amount * (1 - COMMISSION)))
    if lot.seller_id and not lot.is_npc_lot:
        seller = await session.get(Character, lot.seller_id)
        if seller is not None:
            add_currency(seller, bronze=payout)

    lot.buyer_id = winner.id
    lot.sold_at = _now()

    instance.owner_character_id = winner.id
    instance.trade_count = (instance.trade_count or 0) + 1
    if instance.source not in (ItemSource.UNIQUE.value, ItemSource.FESTIVE.value):
        instance.source = ItemSource.AUCTION.value

    session.add(InventoryItem(character_id=winner.id, item_id=item.id,
                              instance_id=instance.id, quantity=1))
    await history.record(session, instance, "sold", winner,
                         detail=detail, price=amount)
    await session.flush()
    return {"ok": True, "lot": lot, "instance": instance, "item": item,
            "amount": amount, "payout": payout}


async def close_finished(session) -> list[dict]:
    """Ударить молотком по истёкшим торгам. Зовётся фоновым циклом бота.

    Три исхода:
      * есть лидер — вещь ему, деньги (уже зарезервированные) продавцу;
      * ставок не было — лот возвращается продавцу штатным путём
        `core/auction._return_to_owner`, чтобы вещь не потерялась;
      * лот успели купить или снять — пропускаем, гонку ловит UPDATE.
    """
    from core.auction import _return_to_owner

    rows = (await session.execute(
        select(AuctionLot)
        .where(AuctionLot.status == AuctionStatus.ACTIVE.value)
        .where(func.coalesce(AuctionLot.start_bid, 0) > 0)
        .where(AuctionLot.expires_at.isnot(None))
        .where(AuctionLot.expires_at < _now())
    )).scalars().all()

    results = []
    for lot in rows:
        winner_id = lot.current_bidder_id
        amount = lot.current_bid or 0
        new_status = (AuctionStatus.SOLD.value if winner_id and amount
                      else AuctionStatus.EXPIRED.value)

        res = await session.execute(
            update(AuctionLot)
            .where(AuctionLot.id == lot.id)
            .where(AuctionLot.status == AuctionStatus.ACTIVE.value)
            .values(status=new_status)
            .execution_options(synchronize_session=False)
        )
        if res.rowcount != 1:
            continue        # успели купить/снять — не наше дело
        lot.status = new_status

        if new_status == AuctionStatus.EXPIRED.value:
            seller = (await session.get(Character, lot.seller_id)
                      if lot.seller_id else None)
            await _return_to_owner(session, lot, seller, event="expired")
            results.append({"lot": lot, "sold": False,
                            "seller_id": lot.seller_id})
            continue

        winner = await session.get(Character, winner_id)
        if winner is None:
            # Победитель удалён: деньги возвращать некому, вещь — продавцу.
            seller = (await session.get(Character, lot.seller_id)
                      if lot.seller_id else None)
            await _return_to_owner(session, lot, seller, event="expired")
            results.append({"lot": lot, "sold": False,
                            "seller_id": lot.seller_id})
            continue

        handed = await _hand_over(session, lot, winner, amount,
                                  detail="выигран на торгах")
        results.append({"lot": lot, "sold": bool(handed.get("ok")),
                        "winner_id": winner_id, "amount": amount,
                        "seller_id": lot.seller_id,
                        "payout": handed.get("payout", 0)})
    await session.flush()
    return results


async def cancel_bid_lot(session, character, lot: AuctionLot) -> dict:
    """Снять свой лот с торгов.

    Снять можно только пока никто не поставил: иначе продавец отменял бы
    невыгодные для себя торги, а участники теряли время.
    """
    from core.auction import _return_to_owner

    if lot.seller_id != character.id:
        return {"ok": False, "reason": "Это не твой лот."}
    if lot.status != AuctionStatus.ACTIVE.value:
        return {"ok": False, "reason": "Лот уже неактивен."}
    if lot.current_bid:
        return {"ok": False,
                "reason": "Ставка уже сделана — торги отменить нельзя."}

    res = await session.execute(
        update(AuctionLot)
        .where(AuctionLot.id == lot.id)
        .where(AuctionLot.status == AuctionStatus.ACTIVE.value)
        .where(func.coalesce(AuctionLot.current_bid, 0) == 0)
        .values(status=AuctionStatus.CANCELLED.value)
        .execution_options(synchronize_session=False)
    )
    if res.rowcount != 1:
        return {"ok": False, "reason": "Кто-то успел поставить — снять нельзя."}
    lot.status = AuctionStatus.CANCELLED.value
    await _return_to_owner(session, lot, character, event="unlisted")
    await session.flush()
    return {"ok": True}


async def active_bid_lots(session, exclude_seller_id: int | None = None,
                          limit: int = 30):
    """Живые торги — витрина «С молотка»."""
    q = (select(AuctionLot)
         .where(AuctionLot.status == AuctionStatus.ACTIVE.value)
         .where(func.coalesce(AuctionLot.start_bid, 0) > 0))
    if exclude_seller_id is not None:
        q = q.where(AuctionLot.seller_id != exclude_seller_id)
    q = q.order_by(AuctionLot.expires_at.asc()).limit(limit)
    return (await session.execute(q)).scalars().all()


async def my_bids(session, character_id: int):
    """Торги, где герой сейчас лидирует, — чтобы видеть свои резервы."""
    return (await session.execute(
        select(AuctionLot)
        .where(AuctionLot.status == AuctionStatus.ACTIVE.value)
        .where(AuctionLot.current_bidder_id == character_id)
        .order_by(AuctionLot.expires_at.asc())
    )).scalars().all()


async def reserved_total(session, character_id: int) -> int:
    """Сколько денег героя сейчас заморожено в ставках."""
    return await session.scalar(
        select(func.coalesce(func.sum(AuctionLot.current_bid), 0))
        .where(AuctionLot.status == AuctionStatus.ACTIVE.value)
        .where(AuctionLot.current_bidder_id == character_id)
    ) or 0
