"""Охота за головами: серверная часть.

Титулы убийц и формула куша общие для обоих стеков и живут в
`engine/bounty.py`. Здесь остаётся работа с БД.
"""
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from engine import bounty as B
from core.models import Character, Mob, MobSpawn

BOUNTY_TITLES = list(B.BOUNTY_TITLES)


async def record_mob_kill(session, spawn: MobSpawn):
    """Фиксирует победу моба над игроком и превращает его в цель охоты."""
    if not spawn:
        return
    spawn.kill_count = (spawn.kill_count or 0) + 1
    if not spawn.bounty_title:
        import random
        spawn.bounty_title = random.choice(BOUNTY_TITLES)
    await session.flush()


async def list_active_bounties(session) -> list[MobSpawn]:
    """Список всех мобов-убийц, за чьи головы объявлена награда."""
    result = await session.execute(
        select(MobSpawn)
        .where(MobSpawn.is_alive == True)
        .where(MobSpawn.kill_count > 0)
        .options(selectinload(MobSpawn.mob), selectinload(MobSpawn.location))
        .order_by(MobSpawn.kill_count.desc())
    )
    return result.scalars().all()


def calculate_bounty_reward(spawn: MobSpawn) -> int:
    """Размер куша за ликвидацию убийцы."""
    return B.reward_for(spawn.kill_count or 1)
