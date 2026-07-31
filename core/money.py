"""Деньги для серверного стека — паритет с engine/money.py.

Разряды, иконки и правила берутся напрямую из `engine.money`, чтобы у
браузерной и серверной версии не завелось двух разных курсов. Здесь
только работа с БД: кошелёк лежит в `Character.gold` (в бронзе), донатные
кристаллы — в `Character.premium`, настройки обмена — в `app_settings`.
"""
from sqlalchemy import select

from core.models import AppSetting, Character
from engine import money as E

BRONZE_PER_SILVER = E.BRONZE_PER_SILVER
SILVER_PER_GOLD = E.SILVER_PER_GOLD
BRONZE_PER_GOLD = E.BRONZE_PER_GOLD
PREMIUM_RATE = E.PREMIUM_RATE
PREMIUM_ICON = E.PREMIUM_ICON
PREMIUM_NAME = E.PREMIUM_NAME
COINS = E.COINS
TUNABLES = E.TUNABLES

# Чистые расчёты и форматирование — общие с браузерным стеком.
split = E.split
total = E.total
fmt = E.fmt
short = E.short
plus = E.plus
coin_line = E.coin_line


async def tune(session, key):
    """Настройка из БД или значение по умолчанию."""
    default = TUNABLES[key][0]
    result = await session.execute(select(AppSetting).where(AppSetting.key == key))
    row = result.scalar_one_or_none()
    if row is None or row.value in (None, ""):
        return default
    try:
        return max(0, int(float(row.value)))
    except (TypeError, ValueError):
        return default


async def set_tunables(session, values):
    """Сохранить настройки валют; пустое значение — вернуть умолчание."""
    for key in TUNABLES:
        if key not in values:
            continue
        raw = values[key]
        result = await session.execute(select(AppSetting).where(AppSetting.key == key))
        row = result.scalar_one_or_none()
        if raw is None or str(raw).strip() == "":
            if row is not None:
                await session.delete(row)
            continue
        try:
            clean = str(max(0, int(float(raw))))
        except (TypeError, ValueError):
            continue
        if row is None:
            session.add(AppSetting(key=key, value=clean))
        else:
            row.value = clean
    await session.commit()


# ── кошелёк персонажа ───────────────────────────────────────

def balance(char):
    return max(0, int(getattr(char, "gold", 0) or 0))


def wallet(char):
    gems = premium(char)
    line = fmt(balance(char))
    return f"{line} · {gems}{PREMIUM_ICON}" if gems else line


def earn(char, amount):
    amount = max(0, int(amount or 0))
    char.gold = balance(char) + amount
    return amount


def can_pay(char, price):
    return balance(char) >= max(0, int(price or 0))


def pay(char, price):
    price = max(0, int(price or 0))
    if balance(char) < price:
        return False
    char.gold = balance(char) - price
    return True


def lack(char, price):
    return max(0, int(price or 0) - balance(char))


# ── премиум ─────────────────────────────────────────────────

def premium(char):
    return max(0, int(getattr(char, "premium", 0) or 0))


def grant_premium(char, amount):
    char.premium = max(0, premium(char) + int(amount or 0))
    return char.premium


def spend_premium(char, amount):
    amount = max(0, int(amount or 0))
    if premium(char) < amount:
        return False
    char.premium = premium(char) - amount
    return True


async def exchange(session, char, gems):
    """Обменять кристаллы на монеты по курсу из БД. Обратного обмена нет."""
    gems = int(gems or 0)
    if gems <= 0:
        return False, "Укажи, сколько кристаллов менять."
    if premium(char) < gems:
        return False, f"Не хватает {gems - premium(char)}{PREMIUM_ICON}."
    rate = await tune(session, "premium_rate")
    if rate <= 0:
        return False, "Обмен кристаллов сейчас закрыт."
    spend_premium(char, gems)
    got = earn(char, gems * rate)
    await session.commit()
    return True, f"Обменяно {gems}{PREMIUM_ICON} → {fmt(got)}"


async def world_totals(session):
    """Сводка по экономике: сколько монет и кристаллов в мире."""
    rows = (await session.execute(select(Character.gold, Character.premium))).all()
    coins = sum(int(g or 0) for g, _ in rows)
    gems = sum(int(pr or 0) for _, pr in rows)
    return {"coins": coins, "coins_text": fmt(coins), "premium": gems}
