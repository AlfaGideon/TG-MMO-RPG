"""Тайный ночной чёрный рынок: редкие контрабандные товары на ротации.

Кроме постоянного ассортимента (`BLACK_MARKET_WARES`) здесь оседают
вещи, изъятые ростовщиком за просрочку залога: «предмет не исчезает из
мира», а меняет владельца. Связка: `core/pawnshop.sweep_expired_loans`
помечает заём `is_liquidated`, а `list_liquidated_wares` показывает эти
вещи на витрине.
"""
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.models import Character, Item, InventoryItem, ItemInstance, PawnLoan


BLACK_MARKET_WARES = [
    {
        "key": "bm_rune_void",
        "name": "🌑 Руна Бездны",
        "desc": "Контрабандная руна тьмы: +12 урон тьмой и +5 к удаче.",
        "cost": 600,
        "type": "rune",
        "rune_key": "rune_void",
    },
    {
        "key": "bm_contraband_chest",
        "name": "📦 Сундук контрабандиста",
        "desc": "Тяжёлый опечатанный сундук со случайными драгоценностями.",
        "cost": 450,
        "type": "chest",
    },
    {
        "key": "bm_shadow_potion",
        "name": "🧪 Эликсир призрачного шага",
        "desc": "Временно защищает от любых засад мобов на 1 час.",
        "cost": 300,
        "type": "potion",
    },
]


def get_black_market_wares() -> list[dict]:
    return BLACK_MARKET_WARES


async def buy_black_market_item(session, character: Character, item_key: str) -> dict:
    from engine.currency import total_in_bronze, deduct_currency, add_currency
    ware = next((w for w in BLACK_MARKET_WARES if w["key"] == item_key), None)
    if not ware:
        return {"ok": False, "reason": "Товар не найден."}

    cost = ware["cost"]
    if total_in_bronze(character) < cost:
        return {"ok": False, "reason": f"Не хватает средств! Нужно {cost}🟤."}

    deduct_currency(character, cost)

    if ware["type"] == "chest":
        # Открываем сундук контрабанды
        add_currency(character, bronze=650)
        character.experience = (character.experience or 0) + 150
        msg = f"Ты открыл {ware['name']} и обнаружил +650🟤 золотом и +150⭐ опыта!"
    else:
        msg = f"Ты приобрёл {ware['name']} на чёрном рынке за {cost}🟤!"

    await session.flush()
    return {"ok": True, "title": "Тайная сделка", "desc": msg}


# Наценка перекупщика на изъятый залог: он выкупил вещь за долг и
# перепродаёт дороже — иначе выгоднее было бы не выкупать свой залог,
# а ждать конфискации и покупать его же дешевле.
LIQUIDATED_MARKUP = 1.35


def liquidated_price(loan: PawnLoan) -> int:
    """Цена изъятого залога на витрине."""
    base = loan.buyback_price or loan.loan_bronze or 1
    return max(1, int(base * LIQUIDATED_MARKUP))


async def list_liquidated_wares(session, limit: int = 10) -> list[dict]:
    """Изъятые за просрочку вещи, выставленные на чёрном рынке."""
    result = await session.execute(
        select(PawnLoan)
        .where(PawnLoan.is_liquidated == True)     # noqa: E712
        .where(PawnLoan.is_redeemed == False)      # noqa: E712
        .options(selectinload(PawnLoan.instance))
        .order_by(PawnLoan.id.desc())
        .limit(limit)
    )
    wares = []
    for loan in result.scalars().all():
        item = await session.get(Item, loan.item_id)
        if item is None:
            continue
        wares.append({
            "loan_id": loan.id,
            "name": item.name,
            "instance": loan.instance,
            "cost": liquidated_price(loan),
        })
    return wares


async def buy_liquidated_item(session, character: Character, loan_id: int) -> dict:
    """Выкупить изъятый залог с витрины: вещь переходит покупателю."""
    from engine.currency import total_in_bronze, deduct_currency

    loan = await session.get(PawnLoan, loan_id)
    if loan is None or not loan.is_liquidated or loan.is_redeemed:
        return {"ok": False, "reason": "Этот товар уже продан."}

    cost = liquidated_price(loan)
    if total_in_bronze(character) < cost:
        return {"ok": False, "reason": f"Не хватает средств! Нужно {cost}🟤."}

    item = await session.get(Item, loan.item_id)
    deduct_currency(character, cost)
    session.add(InventoryItem(
        character_id=character.id,
        item_id=loan.item_id,
        instance_id=loan.instance_id,
        quantity=1,
    ))
    # Заём закрыт окончательно: вещь ушла в чужие руки и больше не висит
    # на витрине (иначе её купили бы дважды).
    loan.is_redeemed = True
    await session.flush()

    return {
        "ok": True,
        "title": "Тайная сделка",
        "desc": (f"Ты выкупил <b>{item.name if item else 'вещь'}</b> "
                 f"с чёрного рынка за {cost}🟤.\n\n"
                 f"<i>Прежний владелец не сумел вернуть долг вовремя.</i>"),
    }
