"""Админка видит подсистемы, которые раньше в ней не упоминались.

Запуск: python3 -m pytest -q tests/test_admin_subsystems.py

Зачем. Grep по `admin/main.py` показывал **0 вхождений** слов invest,
pawnshop, lunar, guild, karma, blackmarket: владелец не мог ни увидеть,
ни поправить эти механики, хотя игроки ими уже пользуются. Набор
проверяет, что страница `/editor/subsystems` и карма в карточке игрока
существуют, отдают 200 и показывают реальные данные из БД.
"""
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import async_session
from core.models import Character, Location, PawnLoan, TownInvestment, User


def _rand_tg():
    return random.randint(100_000_000, 999_999_999)


@pytest.fixture(scope="module")
def client():
    from starlette.testclient import TestClient
    from admin.main import app

    with TestClient(app) as c:
        yield c


def test_routes_exist():
    """Маршруты подсистем зарегистрированы в приложении."""
    from admin.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/editor/subsystems" in paths
    assert "/editor/subsystems/pay-dividends" in paths
    assert "/editor/subsystems/loan/{loan_id}/liquidate" in paths


def test_subsystems_page_renders_all_sections(client):
    """Страница открывается и содержит все шесть блоков."""
    res = client.get("/editor/subsystems")
    assert res.status_code == 200
    for marker in ("Ломбард", "Вклады в городские лавки", "Карма героев",
                   "Фаза луны", "Гильдии", "Чёрный рынок"):
        assert marker in res.text, f"нет блока «{marker}»"

    # Товары рынка берутся из core/blackmarket.py, а не зашиты в шаблон.
    from core import blackmarket as core_bm
    assert core_bm.get_black_market_wares()[0]["name"] in res.text


def test_sidebar_links_to_subsystems(client):
    """Ссылка на подсистемы есть в боковом меню (иначе страницу не найти)."""
    res = client.get("/editor/subsystems")
    assert 'href="/editor/subsystems"' in res.text


@pytest.mark.asyncio
async def test_page_shows_real_loans_and_investments():
    """Займы и вклады из БД попадают на страницу с суммами."""
    from starlette.testclient import TestClient
    from admin.main import app

    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="subsys")
        session.add(user)
        await session.flush()
        char = Character(user_id=user.id, name="SubsysHero",
                         character_class="warrior", level=4, stats_locked=True)
        session.add(char)
        loc = Location(name="Лавочный Погост", description="—",
                       location_type="safe", min_level=1)
        session.add(loc)
        await session.flush()

        session.add(TownInvestment(location_id=loc.id, character_id=char.id,
                                   invested_bronze=777, earned_dividends=13))
        await session.commit()
        char_name, loc_name = char.name, loc.name

    with TestClient(app) as client:
        res = client.get("/editor/subsystems")
        assert res.status_code == 200
        assert char_name in res.text
        assert loc_name in res.text
        assert "777" in res.text          # сумма вклада видна владельцу


@pytest.mark.asyncio
async def test_manual_dividend_payout_credits_investor():
    """Кнопка ручной выплаты действительно начисляет дивиденды."""
    from starlette.testclient import TestClient
    from admin.main import app
    from core import investments as core_inv
    from engine.currency import total_in_bronze

    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="divadmin")
        session.add(user)
        await session.flush()
        char = Character(user_id=user.id, name="DivHero", character_class="warrior",
                         level=4, gold=0, silver=0, bronze=0, stats_locked=True)
        session.add(char)
        loc = Location(name="Дивидендный Тракт", description="—",
                       location_type="safe", min_level=1)
        session.add(loc)
        await session.flush()
        session.add(TownInvestment(location_id=loc.id, character_id=char.id,
                                   invested_bronze=5000, earned_dividends=0))
        await session.commit()
        char_id = char.id
        before = total_in_bronze(char)

    with TestClient(app) as client:
        res = client.post("/editor/subsystems/pay-dividends", follow_redirects=False)
        assert res.status_code == 303

    async with async_session() as session:
        char = await session.get(Character, char_id)
        expected = int(5000 * core_inv.DIVIDEND_RATE)
        assert total_in_bronze(char) == before + expected


@pytest.mark.asyncio
async def test_karma_visible_and_editable_in_player_card():
    """Карма показана в карточке игрока и правится с клампом границ."""
    from starlette.testclient import TestClient
    from admin.main import app
    from core import karma as core_karma

    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="karmaadmin")
        session.add(user)
        await session.flush()
        char = Character(user_id=user.id, name="KarmaCard", character_class="paladin",
                         level=3, karma_score=core_karma.PIOUS_KARMA,
                         stats_locked=True)
        session.add(char)
        await session.commit()
        char_id = char.id

    with TestClient(app) as client:
        res = client.get(f"/player/{char_id}")
        assert res.status_code == 200
        assert 'name="karma_score"' in res.text
        assert "Благочестивый праведник" in res.text

        form = {
            "name": "KarmaCard", "character_class": "paladin", "level": "3",
            "gold": "0", "experience": "0", "strength": "10", "agility": "10",
            "intelligence": "10", "endurance": "10", "luck": "10",
            "max_hp": "100", "max_mp": "50", "current_hp": "100",
            "current_mp": "50", "karma_score": "-9999",     # заведомо за границей
        }
        assert client.post(f"/player/{char_id}/edit", data=form,
                           follow_redirects=False).status_code == 303

    async with async_session() as session:
        char = await session.get(Character, char_id)
        assert char.karma_score == core_karma.MIN_KARMA, "кламп нижней границы"


@pytest.mark.asyncio
async def test_overdue_loan_can_be_liquidated():
    """Просроченный залог помечается изъятым, действующий — нет."""
    from datetime import timedelta

    from starlette.testclient import TestClient
    from admin.main import app
    from core import dates
    from core.loot import new_uid
    from core.models import Item, ItemInstance

    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="overdue")
        session.add(user)
        await session.flush()
        char = Character(user_id=user.id, name="Overdue", character_class="warrior",
                         level=4, stats_locked=True)
        session.add(char)
        item = Item(name="Залоговый меч", description="—", item_type="weapon",
                    rarity="rare", price=300)
        session.add(item)
        await session.flush()
        inst = ItemInstance(uid=new_uid(), item_id=item.id, quality=100)
        session.add(inst)
        await session.flush()

        loan = PawnLoan(character_id=char.id, instance_id=inst.id, item_id=item.id,
                        loan_bronze=200, buyback_price=230, is_redeemed=False,
                        is_liquidated=False,
                        expires_at=dates.utcnow() - timedelta(days=1))
        session.add(loan)
        await session.commit()
        loan_id = loan.id

    with TestClient(app) as client:
        page = client.get("/editor/subsystems")
        assert "просрочен" in page.text
        res = client.post(f"/editor/subsystems/loan/{loan_id}/liquidate",
                          follow_redirects=False)
        assert res.status_code == 303

    async with async_session() as session:
        loan = await session.get(PawnLoan, loan_id)
        assert loan.is_liquidated is True

    # Повторное изъятие ничего не ломает и не меняет статус.
    with TestClient(app) as client:
        assert client.post(f"/editor/subsystems/loan/{loan_id}/liquidate",
                           follow_redirects=False).status_code == 303
