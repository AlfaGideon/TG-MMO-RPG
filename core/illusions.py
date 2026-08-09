"""Иллюзорные стены и тайные гроты мира."""
from core.models import Character, Cell


async def reveal_illusory_wall(session, character: Character, cell: Cell) -> dict:
    """Развеять иллюзию фальшивой стены и открыть тайный проход."""
    if not cell.is_illusory_wall:
        return {"ok": False, "reason": "Это обычная крепкая каменная стена."}

    cell.is_illusory_wall = False
    cell.is_passable = True
    cell.tile_type = "road"
    cell.name = "Тайный грот"
    cell.description = "Скрытая ниша в стене, где укрыт сундук с древними реликвиями."
    cell.has_chest = True
    cell.chest_tier = 2

    character.experience = (character.experience or 0) + 100
    await session.flush()

    return {
        "ok": True,
        "title": "✨ ИЛЛЮЗИЯ РАЗВЕЯНА!",
        "desc": "Стена замерцала и растаяла в воздухе, открыв потайной грот с сокровищами! (+100⭐ опыта)",
    }
