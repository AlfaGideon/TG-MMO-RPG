import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Детерминизм (пункт № 5): игровой random спинован своей константой,
# а уникальные telegram_id берутся вне seed — см. tests/_seed.py.
from _seed import pin, unique_id  # noqa: E402

pin(111)

from core.database import async_session
from core.models import User, Character, Location, Item, ItemInstance, InventoryItem, Party
from core import guilds as core_guilds
from core import mentorship as core_mentorship
from core import duels as core_duels


def _rand_tg():
    return unique_id()


@pytest.mark.asyncio
async def test_guild_founding_and_vault():
    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="guild_founder")
        session.add(user)
        await session.flush()

        char = Character(user_id=user.id, name="GuildLead", character_class="warrior", level=5, gold=30, stats_locked=True)
        session.add(char)
        await session.flush()

        # Create guild
        g_name = f"Орден Зари {_rand_tg()}"
        res = await core_guilds.create_guild(session, char, g_name, "Хранители света")
        assert res["ok"]
        guild = res["guild"]
        assert guild.name == g_name
        assert guild.treasury_bronze == 500

        # Deposit to treasury
        dep_res = await core_guilds.deposit_guild_treasury(session, char, guild, 1000)
        assert dep_res["ok"]
        assert guild.treasury_bronze == 1500

        # Vault item deposit
        item = Item(name="Щит Стража", description="Тяжёлый щит", item_type="armor", price=150)
        session.add(item)
        await session.flush()

        inv = InventoryItem(character_id=char.id, item_id=item.id, quantity=1)
        session.add(inv)
        await session.flush()

        v_res = await core_guilds.deposit_guild_vault(session, char, guild, inv)
        assert v_res["ok"]

        items_in_vault = (await session.execute(
            core_guilds.select(core_guilds.GuildVaultItem).where(core_guilds.GuildVaultItem.guild_id == guild.id)
        )).scalars().all()
        assert len(items_in_vault) == 1


@pytest.mark.asyncio
async def test_mentorship_system():
    async with async_session() as session:
        u_mentor = User(telegram_id=_rand_tg(), username="veteran_hero")
        u_appr = User(telegram_id=_rand_tg(), username="novice_hero")
        session.add_all([u_mentor, u_appr])
        await session.flush()

        c_mentor = Character(user_id=u_mentor.id, name="OldSensei", character_class="paladin", level=10, stats_locked=True)
        c_appr = Character(user_id=u_appr.id, name="YoungPadawan", character_class="warrior", level=2, stats_locked=True)
        session.add_all([c_mentor, c_appr])
        await session.flush()

        # Bind mentor
        bind_res = await core_mentorship.bind_mentor(session, c_appr, c_mentor)
        assert bind_res["ok"]
        assert c_appr.mentor_character_id == c_mentor.id

        # Progress reward
        pts = await core_mentorship.reward_mentor_for_progress(session, c_appr, 50)
        assert pts == 50
        assert c_mentor.honor_points == 50

        bonuses = core_mentorship.get_mentorship_bonuses(c_appr)
        assert bonuses["has_mentor"]
        assert bonuses["exp_bonus_pct"] == 25


@pytest.mark.asyncio
async def test_wager_duels_resolution():
    async with async_session() as session:
        u1 = User(telegram_id=_rand_tg(), username="duelist_a")
        u2 = User(telegram_id=_rand_tg(), username="duelist_b")
        session.add_all([u1, u2])
        await session.flush()

        c_a = Character(user_id=u1.id, name="ChampionA", character_class="warrior", level=6, gold=10, strength=30, stats_locked=True)
        c_b = Character(user_id=u2.id, name="ChampionB", character_class="rogue", level=6, gold=10, strength=28, stats_locked=True)
        session.add_all([c_a, c_b])
        await session.flush()

        # Resolve wager duel (pot = 1000 * 2 = 2000, payout = 1900)
        res = await core_duels.resolve_wager_duel(session, c_a, c_b, wager_bronze=1000)
        assert res["ok"]
        assert res["payout"] == 1900
        assert res["rounds"] >= 1
        assert "winner_name" in res
