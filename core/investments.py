"""Инвестиции в городские лавки и выплата дивидендов."""
from sqlalchemy import select, func
from core.models import Character, TownInvestment, Location


async def invest_in_town(session, character: Character, location_id: int, bronze_amount: int) -> dict:
    """Вложить средства в развитие лавки поселения."""
    from engine.currency import total_in_bronze, deduct_currency

    if bronze_amount <= 0:
        return {"ok": False, "reason": "Сумма должна быть больше нуля."}
    if total_in_bronze(character) < bronze_amount:
        return {"ok": False, "reason": f"Не хватает {bronze_amount - total_in_bronze(character)}🟤."}

    loc = await session.get(Location, location_id)
    if not loc:
        return {"ok": False, "reason": "Локация не найдена."}

    deduct_currency(character, bronze_amount)

    result = await session.execute(
        select(TownInvestment)
        .where(TownInvestment.location_id == location_id)
        .where(TownInvestment.character_id == character.id)
    )
    inv = result.scalar_one_or_none()
    if inv is None:
        inv = TownInvestment(
            location_id=location_id,
            character_id=character.id,
            invested_bronze=bronze_amount,
            earned_dividends=0,
        )
        session.add(inv)
    else:
        inv.invested_bronze = (inv.invested_bronze or 0) + bronze_amount

    await session.flush()
    return {
        "ok": True,
        "invested": bronze_amount,
        "total_invested": inv.invested_bronze,
        "location_name": loc.name,
    }


async def get_town_investment_summary(session, location_id: int, character_id: int) -> dict:
    """Сводка инвестиций в конкретную локацию."""
    total_pool = await session.scalar(
        select(func.sum(TownInvestment.invested_bronze))
        .where(TownInvestment.location_id == location_id)
    ) or 0

    my_inv = (await session.execute(
        select(TownInvestment)
        .where(TownInvestment.location_id == location_id)
        .where(TownInvestment.character_id == character_id)
    )).scalar_one_or_none()

    my_bronze = my_inv.invested_bronze if my_inv else 0
    my_divs = my_inv.earned_dividends if my_inv else 0
    share_pct = int((my_bronze / total_pool) * 100) if total_pool > 0 else 0

    return {
        "total_pool": total_pool,
        "my_invested": my_bronze,
        "my_dividends": my_divs,
        "share_pct": share_pct,
    }
