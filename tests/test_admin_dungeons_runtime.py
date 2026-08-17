"""Runtime regressions for the server-side dungeon editor."""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from starlette.requests import Request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._seed import unique_id
from core.database import async_session
from core.dungeons import is_portal_open, sweep_expired_portals
from core.models import Character, DungeonRun, DungeonTemplate, User
from admin.main import app, dungeon_template_delete, editor_dungeons


def _owner_request(path: str, method: str = "GET") -> Request:
    """A direct/local admin request; no role means unrestricted owner."""
    return Request({
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8000),
        "app": app,
    })


@pytest.mark.asyncio
async def test_dungeon_page_renders_active_run_after_session_closes():
    """An active run must not trigger DetachedInstanceError in Jinja."""
    async with async_session() as session:
        user = User(telegram_id=unique_id(), username="dungeon_admin_runtime")
        session.add(user)
        await session.flush()
        char = Character(
            user_id=user.id,
            name="Герой активного забега",
            character_class="warrior",
            stats_locked=True,
        )
        template = DungeonTemplate(name="Шаблон активного забега", is_active=True)
        session.add_all([char, template])
        await session.flush()
        run = DungeonRun(
            character_id=char.id,
            template_id=template.id,
            seed=123,
            floor=2,
            is_active=True,
        )
        session.add(run)
        await session.commit()
        template_id = template.id
        run_id = run.id

    response = await editor_dungeons(_owner_request("/editor/dungeons"))
    body = response.body.decode("utf-8")
    assert response.status_code == 200
    assert "Герой активного забега" in body
    assert "Шаблон активного забега" in body

    # PostgreSQL enforces this FK: deleting a template must first detach both
    # active and historical runs instead of returning HTTP 500.
    response = await dungeon_template_delete(
        _owner_request(f"/editor/dungeons/{template_id}/delete", "POST"),
        template_id,
    )
    assert response.status_code == 303

    async with async_session() as session:
        assert await session.get(DungeonTemplate, template_id) is None
        saved_run = await session.get(DungeonRun, run_id)
        assert saved_run is not None
        assert saved_run.template_id is None


@pytest.mark.asyncio
async def test_expired_portal_sweep_exists_and_closes_portal():
    """The shared helper used by both the admin page and BotRunner must work."""
    opened_at = datetime.now(timezone.utc) - timedelta(hours=3)
    async with async_session() as session:
        template = DungeonTemplate(
            name="Просроченный портал runtime",
            is_active=True,
            portal_opened_at=opened_at,
        )
        session.add(template)
        await session.commit()
        template_id = template.id

        closed = await sweep_expired_portals(session)
        await session.commit()

        assert [item.id for item in closed] == [template_id]
        assert template.portal_closed_at is not None
        assert is_portal_open(template) is False
