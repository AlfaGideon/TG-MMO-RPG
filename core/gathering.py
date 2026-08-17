"""Рыбалка и гербализм: серверная часть.

Таблицы шансов, суммы и тексты — общие для обоих стеков и живут в
`engine/gathering.py`. Здесь остаётся только работа с БД: начисление
предметов и опыта конкретному персонажу.
"""
from sqlalchemy import select

from engine import gathering as G
from core.models import Character, Item, InventoryItem


async def fish_on_water(session, character: Character) -> dict:
    """Ловля рыбы в реках и озёрах."""
    from engine.currency import add_currency

    kind, amount, exp = G.roll_fish()
    if kind == "heal":
        character.current_hp = min(character.max_hp or 100,
                                   (character.current_hp or 10) + amount)
    elif kind == "mana":
        character.current_mp = min(character.max_mp or 50,
                                   (character.current_mp or 0) + amount)
    elif kind == "gold":
        add_currency(character, bronze=amount)

    character.experience = (character.experience or 0) + exp
    await session.flush()
    return {"ok": True, "title": "🎣 Рыбалка", "desc": G.fish_text(kind, amount)}


async def gather_herbs(session, character: Character) -> dict:
    """Сбор лечебных трав и ингредиентов в лесах и на болотах."""
    name, desc = G.roll_herb()
    character.experience = (character.experience or 0) + G.HERB_EXP

    herb_item = (await session.execute(
        select(Item).where(Item.name == name)
    )).scalars().first()
    if not herb_item:
        herb_item = Item(name=name, description=desc, item_type="material",
                         price=G.HERB_PRICE)
        session.add(herb_item)
        await session.flush()

    session.add(InventoryItem(character_id=character.id,
                              item_id=herb_item.id, quantity=1))
    await session.flush()

    return {"ok": True, "title": "🌿 Травничество", "desc": G.herb_text(name)}
