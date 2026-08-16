"""Иллюзорные стены: серверная часть.

Награда и тексты общие для обоих стеков и живут в
`engine/illusions.py`. Здесь остаётся работа с клеткой в БД.
"""
from engine import illusions as I
from core.models import Character, Cell


async def reveal_illusory_wall(session, character: Character, cell: Cell) -> dict:
    """Развеять иллюзию фальшивой стены и открыть тайный проход."""
    if not cell.is_illusory_wall:
        return {"ok": False, "reason": I.FAIL_TEXT}

    cell.is_illusory_wall = False
    cell.is_passable = True
    cell.tile_type = "road"
    cell.name = I.GROTTO_NAME
    cell.description = I.GROTTO_DESC
    cell.has_chest = True
    cell.chest_tier = I.GROTTO_TIER

    character.experience = (character.experience or 0) + I.REVEAL_EXP
    await session.flush()

    return {
        "ok": True,
        "title": I.TITLE,
        "desc": I.DESC,
    }
