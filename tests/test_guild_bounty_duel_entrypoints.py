"""Гильдии, наставничество, перерождение, награды за головы и дуэли в боте.

Запуск: python3 -m pytest -q tests/test_guild_bounty_duel_entrypoints.py

Зачем. Пять подсистем были написаны и покрыты юнит-тестами, но игрок не
мог до них добраться:
  • `core/guilds.py`, `core/mentorship.py`, `core/prestige.py`,
    `core/duels.py`, `core/bounty.py` импортировались только из `tests/`;
  • кнопка «⚔️ Напасть на игрока» (`pvp_select`) и `bounty_track:` были
    в клавиатурах, но **без обработчиков** — нажатие не делало ничего;
  • `core/bounty.record_mob_kill` не вызывался ниоткуда, поэтому доска
    наград всегда оставалась пустой.

Здесь проверяется связка «кнопка → зарегистрированный хендлер → доменная
функция меняет БД», а не сама доменная логика.
"""
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import async_session
from core.models import Character, Location, Mob, MobSpawn, User


def _rand_tg():
    return random.randint(100_000_000, 999_999_999)


class _FakeCallback:
    """Минимальный объект под magic-фильтры aiogram (нужно только .data)."""

    def __init__(self, data):
        self.data = data


def _has_handler(router, callback_data: str) -> bool:
    probe = _FakeCallback(callback_data)
    for handler in router.callback_query.handlers:
        for flt in handler.filters or []:
            try:
                if flt.callback(probe):
                    return True
            except Exception:
                continue
    return False


# ── кнопки и роутеры ────────────────────────────────────────

def test_main_menu_has_new_sections():
    from bot.keyboards.inline import main_menu_keyboard

    kb = main_menu_keyboard(has_character=True)
    data = [b.callback_data for row in kb.inline_keyboard for b in row]
    for cb in ("guild_menu", "mentor_menu", "bounty_menu"):
        assert cb in data, f"нет кнопки {cb} в главном меню"


def test_rebirth_button_only_for_eligible_heroes():
    """Перерождение не дразнит новичков: кнопка появляется по флагу."""
    from bot.keyboards.inline import profile_book_keyboard

    titles = ["📊 Характеристики", "🎒 Снаряжение"]
    without = profile_book_keyboard(0, 2, titles, free_points=0, can_rebirth=False)
    assert "rebirth_menu" not in [b.callback_data for row in without.inline_keyboard
                                  for b in row]
    with_btn = profile_book_keyboard(0, 2, titles, free_points=0, can_rebirth=True)
    assert "rebirth_menu" in [b.callback_data for row in with_btn.inline_keyboard
                              for b in row]


def test_guild_tables_registered_in_metadata():
    """Таблицы гильдий попадают в Base.metadata и потому создаются.

    Регрессия на реальный баг: модели `Guild`/`GuildVaultItem` объявлены в
    `core/guilds.py`, а миграции импортировали только `core/models.py` —
    таблицы не создавались никогда, и любая работа с гильдиями падала с
    «no such table: guilds». Лечится импортом в `core/migrations.py`.
    """
    import core.migrations  # noqa: F401  (регистрирует модели в metadata)
    from core.models import Base

    for table in ("guilds", "guild_members", "guild_vault_items"):
        assert table in Base.metadata.tables, f"таблица {table} не зарегистрирована"


def test_guild_router_registered_in_bot():
    """Новый роутер подключён — иначе кнопки были бы мертвы."""
    from bot.handlers import routers
    from bot.handlers.guilds import router as guilds_router

    assert guilds_router in routers


def test_handlers_registered():
    from bot.handlers.guilds import router as guilds_router
    from bot.handlers.world_extra import router as world_router

    for cb in ("guild_menu", "guild_create", "guild_join:1", "guild_deposit:100",
               "mentor_menu", "mentor_bind:1", "rebirth_menu", "rebirth_do"):
        assert _has_handler(guilds_router, cb), f"нет обработчика {cb}"

    # Эти две кнопки существовали без обработчиков — главная находка.
    for cb in ("pvp_select", "duel_go:1:100", "bounty_menu", "bounty_track:1"):
        assert _has_handler(world_router, cb), f"нет обработчика {cb}"

    assert not _has_handler(guilds_router, "выдуманная_кнопка")


# ── доменные сценарии ───────────────────────────────────────

@pytest.mark.asyncio
async def test_guild_create_join_and_deposit():
    """Основание, вступление и взнос в казну меняют БД."""
    from sqlalchemy import select

    from core import guilds as core_guilds
    from core.guilds import Guild, guild_members
    from engine.currency import add_currency, total_in_bronze

    async with async_session() as session:
        leader_user = User(telegram_id=_rand_tg(), username="leader")
        member_user = User(telegram_id=_rand_tg(), username="member")
        session.add_all([leader_user, member_user])
        await session.flush()
        leader = Character(user_id=leader_user.id, name="GuildLeader",
                           character_class="warrior", level=9, stats_locked=True)
        member = Character(user_id=member_user.id, name="GuildMember",
                           character_class="rogue", level=4, stats_locked=True)
        session.add_all([leader, member])
        await session.flush()

        # Без денег гильдию не основать.
        poor = await core_guilds.create_guild(session, leader, "Нищий Дом")
        assert poor["ok"] is False

        add_currency(leader, bronze=5000)
        # Имя уникально в пределах общей тестовой БД, поэтому случайный суффикс:
        # соседние наборы тоже создают гильдии и заняли бы фиксированное имя.
        guild_name = f"Дом Испытаний {random.randint(1000, 9999)}"
        res = await core_guilds.create_guild(session, leader, guild_name)
        assert res["ok"] is True
        guild = res["guild"]

        # Повторное имя не принимается.
        dup = await core_guilds.create_guild(session, leader, guild_name)
        assert dup["ok"] is False

        # Вступление второго героя.
        from sqlalchemy import insert
        await session.execute(insert(guild_members).values(
            guild_id=guild.id, character_id=member.id, role="member"))
        await session.flush()

        rows = (await session.execute(
            select(guild_members.c.character_id)
            .where(guild_members.c.guild_id == guild.id)
        )).all()
        assert len(rows) == 2

        before_purse = total_in_bronze(leader)
        before_treasury = guild.treasury_bronze or 0
        dep = await core_guilds.deposit_guild_treasury(session, leader, guild, 500)
        assert dep["ok"] is True
        assert dep["treasury"] == before_treasury + 500
        assert total_in_bronze(leader) == before_purse - 500
        await session.commit()


@pytest.mark.asyncio
async def test_mentorship_rules_and_binding():
    """Наставник — только 8+, ученик — только 1–5, и один раз."""
    from core import mentorship as core_mentor

    async with async_session() as session:
        u1, u2, u3 = (User(telegram_id=_rand_tg(), username=f"m{i}") for i in range(3))
        session.add_all([u1, u2, u3])
        await session.flush()
        mentor = Character(user_id=u1.id, name="Veteran", character_class="warrior",
                           level=10, stats_locked=True)
        pupil = Character(user_id=u2.id, name="Rookie", character_class="mage",
                          level=3, stats_locked=True)
        weak_mentor = Character(user_id=u3.id, name="Weakling",
                                character_class="rogue", level=4, stats_locked=True)
        session.add_all([mentor, pupil, weak_mentor])
        await session.flush()

        assert (await core_mentor.bind_mentor(session, pupil, weak_mentor))["ok"] is False
        assert (await core_mentor.bind_mentor(session, mentor, mentor))["ok"] is False

        res = await core_mentor.bind_mentor(session, pupil, mentor)
        assert res["ok"] is True
        assert pupil.mentor_character_id == mentor.id

        # Второго наставника взять нельзя.
        assert (await core_mentor.bind_mentor(session, pupil, mentor))["ok"] is False

        bonuses = core_mentor.get_mentorship_bonuses(pupil)
        assert bonuses["has_mentor"] and bonuses["exp_bonus_pct"] == 25

        gained = await core_mentor.reward_mentor_for_progress(session, pupil)
        assert gained > 0 and (mentor.honor_points or 0) >= gained
        await session.commit()


@pytest.mark.asyncio
async def test_rebirth_requires_level_and_boosts_stats():
    """Перерождение доступно с порога и даёт +10 % к статам."""
    from core import prestige as core_prestige

    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="reborn")
        session.add(user)
        await session.flush()
        char = Character(user_id=user.id, name="Reborn", character_class="warrior",
                         level=5, strength=20, stats_locked=True)
        session.add(char)
        await session.flush()

        assert core_prestige.can_rebirth(char)[0] is False
        assert (await core_prestige.perform_rebirth(session, char))["ok"] is False

        char.level = core_prestige.REBIRTH_MIN_LEVEL
        char.experience = 500
        before_str = char.strength
        assert core_prestige.can_rebirth(char)[0] is True

        res = await core_prestige.perform_rebirth(session, char)
        assert res["ok"] is True
        assert char.level == 1 and char.experience == 0
        assert char.rebirth_count == 1
        assert char.strength > before_str, "Искра Бессмертия не подняла статы"
        await session.commit()


@pytest.mark.asyncio
async def test_bounty_appears_after_mob_kills_player():
    """Убийца игрока получает имя и попадает на доску наград."""
    from core import bounty as core_bounty

    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="victim")
        session.add(user)
        await session.flush()
        loc = Location(name="Тракт Убийц", description="—",
                       location_type="dangerous", min_level=1)
        mob = Mob(name="Лютый ворг", description="—", level=5, hp=60,
                  damage=12, defense=3, exp_reward=40, gold_reward=20)
        session.add_all([loc, mob])
        await session.flush()
        spawn = MobSpawn(mob_id=mob.id, location_id=loc.id,
                         home_location_id=loc.id, is_alive=True, current_hp=60)
        session.add(spawn)
        await session.flush()

        # До первой жертвы доска пуста для этого спавна.
        before = await core_bounty.list_active_bounties(session)
        assert all(b.id != spawn.id for b in before)

        await core_bounty.record_mob_kill(session, spawn)
        assert spawn.kill_count == 1
        assert spawn.bounty_title, "убийце не присвоено имя"

        after = await core_bounty.list_active_bounties(session)
        assert any(b.id == spawn.id for b in after), "цель не попала на доску"

        reward_one = core_bounty.calculate_bounty_reward(spawn)
        await core_bounty.record_mob_kill(session, spawn)
        assert core_bounty.calculate_bounty_reward(spawn) > reward_one
        await session.commit()


@pytest.mark.asyncio
async def test_duel_with_wager_moves_money_to_winner():
    """Дуэль списывает ставки и отдаёт банк победителю."""
    from core import duels as core_duels
    from engine.currency import add_currency, total_in_bronze

    async with async_session() as session:
        ua, ub = User(telegram_id=_rand_tg()), User(telegram_id=_rand_tg())
        session.add_all([ua, ub])
        await session.flush()
        a = Character(user_id=ua.id, name="DuelistA", character_class="warrior",
                      level=6, max_hp=120, current_hp=120, stats_locked=True)
        b = Character(user_id=ub.id, name="DuelistB", character_class="rogue",
                      level=6, max_hp=120, current_hp=120, stats_locked=True)
        session.add_all([a, b])
        await session.flush()

        # Без денег ставку не принимают.
        assert (await core_duels.resolve_wager_duel(session, a, b, 1000))["ok"] is False

        add_currency(a, bronze=1000)
        add_currency(b, bronze=1000)
        total_before = total_in_bronze(a) + total_in_bronze(b)

        res = await core_duels.resolve_wager_duel(session, a, b, 200)
        assert res["ok"] is True
        assert res["winner_name"] in (a.name, b.name)
        assert res["rounds"] >= 1 and res["log"]

        # Банк за вычетом комиссии арены: денег в мире стало меньше, не больше.
        total_after = total_in_bronze(a) + total_in_bronze(b)
        assert total_after < total_before, "комиссия арены не удержана"
        assert total_after == total_before - 400 + res["payout"]
        await session.commit()
