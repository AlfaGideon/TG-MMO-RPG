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


# Дивиденды: доля от вклада за один расчётный период. 2 % в сутки —
# вклад окупается примерно за 50 дней, поэтому инвестиции остаются
# долгой целью, а не заменой добыче.
DIVIDEND_RATE = 0.02
DIVIDEND_PERIOD_HOURS = 24


async def pay_dividends(session) -> list[dict]:
    """Начислить дивиденды всем вкладчикам. Возвращает список выплат.

    Вызывается фоновым циклом бота (`bot/runner.py:_dividend_loop`) раз в
    DIVIDEND_PERIOD_HOURS. Раньше вклады только принимались: колонка
    `earned_dividends` существовала, но никто её не увеличивал, и вкладчик
    не получал ничего.
    """
    from sqlalchemy.orm import selectinload
    from engine.currency import add_currency

    result = await session.execute(
        select(TownInvestment)
        .where(TownInvestment.invested_bronze > 0)
        # user грузим сразу: в async ленивая связь бросает MissingGreenlet
        .options(selectinload(TownInvestment.character).selectinload(Character.user),
                 selectinload(TownInvestment.location))
    )
    payouts = []
    for inv in result.scalars().all():
        amount = int((inv.invested_bronze or 0) * DIVIDEND_RATE)
        if amount <= 0:
            continue
        character = inv.character
        if character is None:                 # вкладчик удалён — пропускаем
            continue
        add_currency(character, bronze=amount)
        inv.earned_dividends = (inv.earned_dividends or 0) + amount
        payouts.append({
            "character_id": character.id,
            "telegram_id": getattr(character.user, "telegram_id", None),
            "amount": amount,
            "location_name": inv.location.name if inv.location else "поселение",
        })
    await session.flush()
    return payouts
