"""Прямой обмен между игроками: «рука в руку» (IDEAS-next, пункт 2).

Экономика знала только посредника-аукцион (комиссия, витрина, 24 часа).
Подарок — это то, чего у аукциона быть не может в принципе: вещь переходит
мгновенно, без комиссии и без согласия получателя. Согласие и не нужно:
подарок ничего не списывает с принимающего, поэтому вектора обмана здесь
нет — отдать можно только своё.

Правила, которые держат честность обмена:

* даритель и получатель стоят на одной клетке (тот же критерий, что у
  дуэлей: `cell_id` + `location_id` + этаж) — «рука в руку» не телепорт;
* надетое и спрятанный в защищённый карман не дарится (снимите/достаньте);
* предметы с `is_sellable=False` (квестовые, уникальные подарки админа)
  не переходят руками — иначе «нерастащимый» артефакт всё равно ушёл бы
  через подарок;
* уникальный экземпляр не делится: только целиком, и проверяется уровень
  получателя (тот же запрет, что при покупке на аукционе);
* перевод монет — только вниз по курсу: считаем и спишем в бронзе
  (`engine/currency`), получатель примет тем, чем умеет.

История экземпляра получает событие `gifted` — летопись предмета (лента
в карточке вещи) показывает обе стороны перехода.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core import history
from core.models import InventoryItem, Item, ItemInstance
from engine.currency import add_currency, deduct_currency, total_in_bronze

# Шаги перевода монет — как ставки дуэли: набор, а не произвольное поле
# (колбэк подделать легче, чем форму; список держим коротким).
GOLD_STEPS = (100, 500, 1000, 5000)


def in_reach(sender, recipient) -> bool:
    """Стоят ли рядом (та же клетка, локация и этаж)."""
    if sender is None or recipient is None or sender.id == recipient.id:
        return False
    return (sender.cell_id == recipient.cell_id
            and sender.location_id == recipient.location_id
            and (sender.floor or 0) == (recipient.floor or 0))


async def giftable_items(session, character) -> list[InventoryItem]:
    """Что можно подарить: не надето, не в кармане, продаваемо."""
    rows = (await session.execute(
        select(InventoryItem)
        .options(selectinload(InventoryItem.item), selectinload(InventoryItem.instance))
        .where(InventoryItem.character_id == character.id)
        .where(InventoryItem.is_equipped == False)  # noqa: E712
        .where(InventoryItem.in_stash == False)    # noqa: E712
        .order_by(InventoryItem.id)
    )).scalars().all()
    out = []
    for row in rows:
        item = row.item
        if item is not None and not item.is_sellable:
            continue
        out.append(row)
    return out


async def gift_item(session, sender, recipient, inv_item: InventoryItem,
                    quantity: int = 1) -> dict:
    """Передать вещь из сумки в сумку. Возвращает {"ok", "reason"?}."""
    if not in_reach(sender, recipient):
        return {"ok": False, "reason": "Получатель больше не рядом."}
    if inv_item is None or inv_item.character_id != sender.id:
        return {"ok": False, "reason": "Эта вещь тебе не принадлежит."}
    if inv_item.is_equipped:
        return {"ok": False, "reason": "Сначала сними предмет."}
    if inv_item.in_stash:
        return {"ok": False, "reason": "Из защищённого кармана не дарят — "
                                       "сначала достань в сумку."}
    # Item/Instance подгружаем явно: в async-сессии ленивая загрузка
    # вне зелёного контекста — это MissingGreenlet, а не «типа работает».
    item = inv_item.item if "item" in inv_item.__dict__ \
        else await session.get(Item, inv_item.item_id)
    if item is None:
        return {"ok": False, "reason": "Предмет пропал из мира."}
    if not item.is_sellable:
        return {"ok": False, "reason": "Этот предмет нельзя передать."}

    name = item.name or "предмет"
    try:
        qty = max(1, int(quantity))
    except (TypeError, ValueError):
        qty = 1

    if inv_item.instance_id is not None:
        # Уникальный экземпляр: только целиком и по уровню — как покупка.
        qty = 1
        if (recipient.level or 1) < (item.level_requirement or 1):
            return {"ok": False,
                    "reason": f"Получателю нужен {item.level_requirement} "
                              "уровень, чтобы владеть этим."}

    have = inv_item.quantity or 1
    if qty > have:
        return {"ok": False, "reason": "Столько штук нет в сумке."}

    if inv_item.instance_id is not None:
        instance = inv_item.instance if "instance" in inv_item.__dict__ \
            else await session.get(ItemInstance, inv_item.instance_id)
        await session.delete(inv_item)
        if instance is not None:
            instance.owner_character_id = recipient.id
            instance.trade_count = (instance.trade_count or 0) + 1
        session.add(InventoryItem(
            character_id=recipient.id, item_id=inv_item.item_id,
            instance_id=inv_item.instance_id, quantity=1,
        ))
        if instance is not None:
            await history.record(session, instance, "gifted", sender,
                                 detail=f"подарен: {recipient.name}")
    else:
        left = have - qty
        if left > 0:
            inv_item.quantity = left
        else:
            await session.delete(inv_item)
        # Стаки расходятся по сумкам без экземпляров: ищем, куда подсыпать.
        target = (await session.execute(
            select(InventoryItem)
            .where(InventoryItem.character_id == recipient.id)
            .where(InventoryItem.item_id == inv_item.item_id)
            .where(InventoryItem.instance_id.is_(None))
            .order_by(InventoryItem.id)
        )).scalars().first()
        if target is not None:
            target.quantity = (target.quantity or 1) + qty
        else:
            session.add(InventoryItem(character_id=recipient.id,
                                      item_id=inv_item.item_id, quantity=qty))
    await session.flush()
    return {"ok": True, "name": name, "qty": qty}


async def gift_gold(session, sender, recipient, bronze: int) -> dict:
    """Перевести монеты (в бронзе; сдача — по правилам `engine.currency`)."""
    if not in_reach(sender, recipient):
        return {"ok": False, "reason": "Получатель больше не рядом."}
    try:
        amount = int(bronze)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "Непонятная сумма."}
    if amount <= 0:
        return {"ok": False, "reason": "Подарок должен быть положительным."}
    have = total_in_bronze(sender)
    if have < amount:
        return {"ok": False, "reason": f"Не хватает {amount - have}🟤."}
    if not deduct_currency(sender, amount):
        return {"ok": False, "reason": "Недостаточно монет."}
    add_currency(recipient, bronze=amount)
    await session.flush()
    return {"ok": True, "amount": amount}
