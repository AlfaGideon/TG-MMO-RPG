"""
Dungeon portal lifecycle helpers, shared by the admin panel and the bot.

A portal opened on the world map stays open for new entries for at most
PORTAL_MAX_LIFETIME (2 hours), or until an admin closes it manually.
Closing a portal only blocks *new* entries — anyone with an already-active
DungeonRun keeps playing (their run references the template by id directly,
independent of the world cell), until they die or leave voluntarily.
"""
from datetime import datetime, timedelta

from sqlalchemy import select

from core.models import Cell, DungeonTemplate

PORTAL_MAX_LIFETIME = timedelta(hours=2)


def _now():
    return datetime.utcnow()


async def close_portal(session, template: DungeonTemplate):
    """Blocks new entries into this template's dungeon: keeps the template
    row itself (so anyone already inside keeps generating floors normally),
    but removes the world-map cell link so the entry button disappears."""
    if template.portal_closed_at is None:
        template.portal_closed_at = _now()

    result = await session.execute(
        select(Cell).where(Cell.dungeon_template_id == template.id)
    )
    for cell in result.scalars().all():
        cell.dungeon_template_id = None
        if cell.tile_type == "portal":
            cell.tile_type = "road"


def is_portal_open(template: DungeonTemplate) -> bool:
    """Pure check: is this template currently accepting new entries?"""
    if template is None or not template.is_active:
        return False
    if template.portal_closed_at is not None:
        return False
    if template.portal_opened_at is not None and _now() - template.portal_opened_at > PORTAL_MAX_LIFETIME:
        return False
    return True


async def sweep_expired_portals(session) -> list[DungeonTemplate]:
    """Auto-closes any portal that has been open longer than
    PORTAL_MAX_LIFETIME. Cheap to call frequently (e.g. on every cell render
    or admin page load) — most calls will find nothing to do."""
    result = await session.execute(
        select(DungeonTemplate)
        .where(DungeonTemplate.portal_closed_at.is_(None))
        .where(DungeonTemplate.portal_opened_at.isnot(None))
    )
    templates = result.scalars().all()
    now = _now()
    closed = []
    for tpl in templates:
        if now - tpl.portal_opened_at > PORTAL_MAX_LIFETIME:
            await close_portal(session, tpl)
            closed.append(tpl)
    return closed
