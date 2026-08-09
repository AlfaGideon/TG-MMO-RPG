"""Тайный ночной чёрный рынок: редкие контрабандные товары на ротации."""
from core.models import Character, Item, InventoryItem


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
