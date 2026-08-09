"""Рыбалка и гербализм на природных клетках мира."""
import random
from sqlalchemy import select
from core.models import Character, Item, InventoryItem


async def fish_on_water(session, character: Character) -> dict:
    """Ловля рыбы в реках и озёрах."""
    from engine.currency import add_currency

    roll = random.random()
    if roll < 0.40:
        # Рыба восстановления сил
        heal_hp = 30
        character.current_hp = min(character.max_hp or 100, (character.current_hp or 10) + heal_hp)
        msg = f"🐟 Ты выудил сочную Глубинную Форель! Она восстановила тебе +{heal_hp} HP."
    elif roll < 0.70:
        # Рыба мудрости
        heal_mp = 20
        character.current_mp = min(character.max_mp or 50, (character.current_mp or 0) + heal_mp)
        msg = f"✨ Ты поймал светящегося Зеркального Карпа! Он восстановил тебе +{heal_mp} MP."
    elif roll < 0.90:
        # Затонувший кошель
        gold_find = random.randint(30, 80)
        add_currency(character, bronze=gold_find)
        msg = f"💰 К крючку прицепился старый затонувший кошель со дна! Найдено +{gold_find}🟤 монет."
    else:
        msg = "🌊 Поплавок покачался на волнах, но рыба сорвалась с крючка. Попробуй ещё раз!"

    character.experience = (character.experience or 0) + 15
    await session.flush()
    return {"ok": True, "title": "🎣 Рыбалка", "desc": msg}


async def gather_herbs(session, character: Character) -> dict:
    """Сбор лечебных трав и ингредиентов в лесах и на болотах."""
    herbs = [
        ("🌿 Лунноцвет", "Редкий светящийся цветок"),
        ("🍄 Пепельник", "Гриб, растущий на пожарищах"),
        ("🌱 Лечебная трава", "Трава с горьким целебным соком"),
    ]
    name, desc = random.choice(herbs)
    character.experience = (character.experience or 0) + 20

    # Добавляем в инвентарь или начисляем опыт
    from core.models import Item, InventoryItem
    herb_item = (await session.execute(select(Item).where(Item.name == name))).scalars().first()
    if not herb_item:
        herb_item = Item(name=name, description=desc, item_type="material", price=15)
        session.add(herb_item)
        await session.flush()

    session.add(InventoryItem(character_id=character.id, item_id=herb_item.id, quantity=1))
    await session.flush()

    return {
        "ok": True,
        "title": "🌿 Травничество",
        "desc": f"Ты аккуратно срезал {name}! Растение аккуратно уложено в сумку (+20⭐ опыта).",
    }
