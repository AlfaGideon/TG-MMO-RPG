"""Трёхвалютная экономика: один кошелёк и одна арифметика в двух стеках.

Запуск: python3 -m pytest -q tests/test_currency_parity.py

Долг реестра паритета (`tests/test_parity.py`, Feature «Трёхвалютная
экономика»): колонки `bronze`/`silver`/`gold` были у обеих моделей, но
движок продолжал начислять и тратить единый `gold` — конвертация 1:100
работала только на сервере.

Здесь проверяется, что теперь оба стека считают деньги одинаково: одна
и та же последовательность операций даёт одинаковый кошелёк у `Player`
(браузерный стек) и у `Character` (серверный).
"""
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import currency
from engine.models import Player


def _rand_tg():
    return random.randint(100_000_000, 999_999_999)


# ── арифметика конвертации ──────────────────────────────────

def test_conversion_carries_up():
    """99+1 бронзы = 1 серебро; 9999+1 = 1 золото."""
    p = Player(tg_id=1)
    p.bronze, p.silver, p.gold = 0, 0, 0

    currency.earn(p, 99)
    assert (p.bronze, p.silver, p.gold) == (99, 0, 0)

    currency.earn(p, 1)
    assert (p.bronze, p.silver, p.gold) == (0, 1, 0), "бронза не свернулась в серебро"

    p.bronze, p.silver, p.gold = 0, 0, 0
    currency.earn(p, 9999)
    assert (p.bronze, p.silver, p.gold) == (99, 99, 0)
    currency.earn(p, 1)
    assert (p.bronze, p.silver, p.gold) == (0, 0, 1), "серебро не свернулось в золото"
    assert currency.total(p) == 10_000


def test_spend_breaks_big_coins():
    """Покупка на 1🟤 при 1🟡 в кошельке разменивает золото."""
    p = Player(tg_id=2)
    p.bronze, p.silver, p.gold = 0, 0, 1        # ровно 10 000 бронзы

    assert currency.can_afford(p, 1)
    assert currency.spend(p, 1) is True
    assert currency.total(p) == 9_999
    assert (p.bronze, p.silver, p.gold) == (99, 99, 0), "размен посчитан неверно"


def test_spend_refuses_and_keeps_wallet_intact():
    """Не хватило — кошелёк не изменился ни на монету."""
    p = Player(tg_id=3)
    p.bronze, p.silver, p.gold = 50, 0, 0

    before = (p.bronze, p.silver, p.gold)
    assert currency.can_afford(p, 51) is False
    assert currency.spend(p, 51) is False
    assert (p.bronze, p.silver, p.gold) == before, "кошелёк тронут при отказе"

    assert currency.spend(p, 50) is True
    assert currency.total(p) == 0


def test_short_formats_by_scale():
    """Мелочь — в бронзе, крупное — золотом и серебром."""
    assert currency.short(0) == "0🟤"
    assert currency.short(99) == "99🟤"
    assert currency.short(100) == "1⚪"
    assert currency.short(150) == "1⚪ 50🟤"
    assert currency.short(10_000) == "1🟡"
    assert currency.short(12_500) == "1🟡 25⚪"


# ── миграция старых сохранений ──────────────────────────────

def test_migration_preserves_buying_power():
    """Старое «золото» переносится в бронзу: покупательная способность та же."""
    raw = {"tg_id": 4, "cls": "berserker", "gold": 300, "level": 5}
    migrated = currency.migrate_raw(dict(raw))
    hero = Player.from_dict(migrated)

    assert currency.total(hero) == 300, "сумма изменилась при миграции"
    assert (hero.bronze, hero.silver, hero.gold) == (300, 0, 0)
    assert hero.level == 5, "прочие поля не пострадали"

    # Повторный прогон ничего не портит (сейв мог загрузиться дважды).
    twice = currency.migrate_raw(currency.migrate_raw(dict(raw)))
    assert twice["bronze"] == 300 and twice["gold"] == 0

    # Уже мигрированный кошелёк не трогаем.
    modern = {"tg_id": 5, "bronze": 10, "silver": 2, "gold": 1,
              "wallet_v": currency.WALLET_VERSION}
    assert currency.migrate_raw(dict(modern)) == modern


def test_new_hero_starts_with_bronze():
    """Стартовый капитал лежит в бронзе, а не в золоте."""
    hero = Player(tg_id=6)
    assert hero.gold == 0, "новый герой не должен стартовать с золотом"
    assert currency.total(hero) == 50
    assert hero.wallet_v == currency.WALLET_VERSION


# ── паритет с серверным стеком ──────────────────────────────

@pytest.mark.asyncio
async def test_same_operations_give_same_wallet_on_both_stacks():
    """Одна последовательность операций → одинаковый кошелёк у Player и Character."""
    from core.database import async_session
    from core.models import Character, User

    operations = [("earn", 7_450), ("spend", 1_200), ("earn", 99),
                  ("spend", 6_349), ("earn", 1)]

    hero = Player(tg_id=7)
    hero.bronze, hero.silver, hero.gold = 0, 0, 0

    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="wallet")
        session.add(user)
        await session.flush()
        char = Character(user_id=user.id, name="Wallet", character_class="warrior",
                         level=3, bronze=0, silver=0, gold=0, stats_locked=True)
        session.add(char)
        await session.flush()

        for action, amount in operations:
            if action == "earn":
                currency.earn(hero, amount)
                currency.earn(char, amount)       # тот же модуль на сервере
            else:
                assert currency.spend(hero, amount) is True
                assert currency.spend(char, amount) is True

            assert (hero.bronze, hero.silver, hero.gold) == \
                   (char.bronze, char.silver, char.gold), \
                   f"кошельки разошлись после {action} {amount}"

        assert currency.total(hero) == currency.total(char)
        assert currency.fmt(hero) == currency.fmt(char)
        await session.rollback()


def test_engine_has_no_raw_gold_arithmetic():
    """В движке не осталось прямых `p.gold += / -=` в обход конвертации."""
    import glob
    import re

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    offenders = []
    pattern = re.compile(r"\.gold\s*(\+=|-=)")
    for path in glob.glob(os.path.join(root, "engine", "*.py")):
        if os.path.basename(path) == "currency.py":
            continue                              # там это описано в docstring
        for num, line in enumerate(open(path, encoding="utf-8"), 1):
            if pattern.search(line):
                offenders.append(f"{os.path.basename(path)}:{num}")
    assert not offenders, f"прямая арифметика по gold: {offenders}"
