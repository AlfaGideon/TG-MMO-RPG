"""Призрачные торговцы: серверная часть.

Каталог товаров, цены в прахе и тексты — общие для обоих стеков и живут
в `engine/spectral.py`. Здесь остаётся работа с БД.
"""
from sqlalchemy import select

from engine import spectral as S
from core.models import Character, InventoryItem, Item, ItemInstance, Grave


SPECTRAL_WARES = S.SPECTRAL_WARES


def get_spectral_wares() -> list[dict]:
    return SPECTRAL_WARES


async def harvest_soul_ash(session, character: Character, grave: Grave) -> dict:
    """Почтить память павшего воина и собрать прах предков."""
    gain = S.ASH_PER_GRAVE
    character.soul_ash = (character.soul_ash or 0) + gain
    await session.flush()
    return {
        "ok": True,
        "gained": gain,
        "total_ash": character.soul_ash,
    }


async def buy_spectral_item(session, character: Character, item_key: str) -> dict:
    ware = S.ware_by_key(item_key)
    if not ware:
        return {"ok": False, "reason": "Товар не найден."}

    cost = ware["cost_ash"]
    if (character.soul_ash or 0) < cost:
        return {"ok": False, "reason": f"Не хватает Праха предков! Требуется {cost} 🕯."}

    character.soul_ash -= cost

    if item_key == "spec_wound_heal":
        from core import death as core_death
        core_death.heal_wounds(character)
        msg = S.buy_text(ware, item_key)
    elif item_key == "spec_ancestor_tear":
        character.max_mp = (character.max_mp or 50) + S.TEAR_MANA_BONUS
        character.current_mp = character.max_mp
        msg = S.buy_text(ware, item_key)
    else:
        msg = S.buy_text(ware, item_key)

    await session.flush()
    return {"ok": True, "title": "Призрачный обмен", "desc": msg}
