"""Ломбард: серверная часть.

Ставки (доля выдачи, комиссия выкупа, срок) — общие для обоих стеков и
живут в `engine/shadowecon.py`. Здесь остаётся работа с БД.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from engine import shadowecon as E
from core.models import Character, InventoryItem, ItemInstance, PawnLoan


def _now():
    return datetime.now(timezone.utc)


async def create_pawn_loan(session, character: Character, inv_item: InventoryItem,
                           days: int = E.LOAN_DAYS) -> dict:
    """Заложить предмет ростовщику под процент."""
    from engine.currency import add_currency
    from core.loot import instance_price

    if inv_item.is_equipped:
        return {"ok": False, "reason": "Сначала сними предмет!"}
    if not inv_item.instance:
        return {"ok": False, "reason": "Ростовщик принимает в залог только именные вещи со своим ID."}

    instance = inv_item.instance
    base_val = instance_price(instance, inv_item.item.price if inv_item.item else 10)
    loan_val = E.loan_for(base_val)
    buyback = E.buyback_for(loan_val)

    # Убираем предмет из сумки
    inst_id = instance.id
    item_id = inv_item.item_id
    await session.delete(inv_item)

    loan = PawnLoan(
        character_id=character.id,
        instance_id=inst_id,
        item_id=item_id,
        loan_bronze=loan_val,
        buyback_price=buyback,
        is_redeemed=False,
        is_liquidated=False,
        expires_at=_now() + timedelta(days=days),
    )
    session.add(loan)

    # Выдаём наличные на руки
    add_currency(character, bronze=loan_val)
    await session.flush()

    return {
        "ok": True,
        "loan_bronze": loan_val,
        "buyback_price": buyback,
        "days": days,
    }


async def redeem_pawn_loan(session, character: Character, loan_id: int) -> dict:
    """Выкупить заложенный предмет из ломбарда."""
    from engine.currency import total_in_bronze, deduct_currency

    loan = await session.get(PawnLoan, loan_id)
    if not loan or loan.is_redeemed or loan.is_liquidated:
        return {"ok": False, "reason": "Этот заём уже закрыт или просрочен."}
    if loan.character_id != character.id:
        return {"ok": False, "reason": "Это чужой заём."}

    if total_in_bronze(character) < loan.buyback_price:
        return {"ok": False, "reason": f"Не хватает {loan.buyback_price - total_in_bronze(character)}🟤 для выкупа."}

    deduct_currency(character, loan.buyback_price)

    # Возвращаем предмет в сумку
    session.add(InventoryItem(
        character_id=character.id,
        item_id=loan.item_id,
        instance_id=loan.instance_id,
        quantity=1,
    ))

    loan.is_redeemed = True
    await session.flush()

    return {
        "ok": True,
        "cost": loan.buyback_price,
    }


async def list_active_loans(session, character_id: int) -> list[PawnLoan]:
    result = await session.execute(
        select(PawnLoan)
        .where(PawnLoan.character_id == character_id)
        .where(PawnLoan.is_redeemed == False)
        .where(PawnLoan.is_liquidated == False)
    )
    return result.scalars().all()


async def sweep_expired_loans(session) -> list[PawnLoan]:
    """Изъять залоги, у которых вышел срок. Возвращает изъятые займы.

    Раньше просроченный залог висел «активным» вечно: игрок не мог его
    выкупить по смыслу, но и ростовщик вещь не забирал. Теперь просрочка
    помечается `is_liquidated`, и вещь попадает на витрину чёрного рынка
    (`core/blackmarket.list_liquidated_wares`).

    Вызывается фоновым циклом бота (`bot/runner.py:_pawnshop_sweep_loop`)
    и кнопкой в админке.
    """
    from core.dates import aware, utcnow

    result = await session.execute(
        select(PawnLoan)
        .where(PawnLoan.is_redeemed == False)      # noqa: E712
        .where(PawnLoan.is_liquidated == False)    # noqa: E712
    )
    now = utcnow()
    liquidated = []
    for loan in result.scalars().all():
        expires = aware(loan.expires_at)
        if expires is not None and now > expires:
            loan.is_liquidated = True
            liquidated.append(loan)
    if liquidated:
        await session.flush()
    return liquidated
