"""Бродячие торговцы-призраки на местах древних могил."""
from sqlalchemy import select
from core.models import Character, InventoryItem, Item, ItemInstance, Grave


SPECTRAL_WARES = [
    {
        "key": "spec_wound_heal",
        "name": "📜 Свиток Очищения Ран",
        "desc": "Мгновенно исцеляет любые кровоточащие раны после смерти.",
        "cost_ash": 30,
    },
    {
        "key": "spec_ethereal_blade",
        "name": "🗡 Эфирный клинок",
        "desc": "Призрачное оружие: +25 урона, игнорирующего броню.",
        "cost_ash": 75,
    },
    {
        "key": "spec_ancestor_tear",
        "name": "💧 Слеза предков",
        "desc": "Навсегда увеличивает максимальный запас маны на +10.",
        "cost_ash": 50,
    },
]


def get_spectral_wares() -> list[dict]:
    return SPECTRAL_WARES


async def harvest_soul_ash(session, character: Character, grave: Grave) -> dict:
    """Почтить память павшего воина и собрать прах предков."""
    gain = 25
    character.soul_ash = (character.soul_ash or 0) + gain
    await session.flush()
    return {
        "ok": True,
        "gained": gain,
        "total_ash": character.soul_ash,
    }


async def buy_spectral_item(session, character: Character, item_key: str) -> dict:
    ware = next((w for w in SPECTRAL_WARES if w["key"] == item_key), None)
    if not ware:
        return {"ok": False, "reason": "Товар не найден."}

    cost = ware["cost_ash"]
    if (character.soul_ash or 0) < cost:
        return {"ok": False, "reason": f"Не хватает Праха предков! Требуется {cost} 🕯."}

    character.soul_ash -= cost

    if item_key == "spec_wound_heal":
        from core import death as core_death
        core_death.heal_wounds(character)
        msg = "Призрачный свет окутал тебя. Все раны мгновенно затянулись!"
    elif item_key == "spec_ancestor_tear":
        character.max_mp = (character.max_mp or 50) + 10
        character.current_mp = character.max_mp
        msg = "Ты испил слезу предков. Максимальная мана увеличена на +10 навсегда!"
    else:
        msg = f"Ты приобрёл {ware['name']} у призрачного торговца за {cost} 🕯 Праха предков!"

    await session.flush()
    return {"ok": True, "title": "Призрачный обмен", "desc": msg}
