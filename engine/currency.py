"""Трёхвалютная система: бронза → серебро → золото (1:100)"""

CONVERSION = 100  # 1 серебро = 100 бронзы, 1 золото = 100 серебра

def normalize_currencies(p):
    """Приводит валюты к каноническому виду (не больше 99 в младшей)."""
    if not hasattr(p, "bronze"):
        return

    bronze = getattr(p, "bronze", 0) or 0
    silver = getattr(p, "silver", 0) or 0
    gold = getattr(p, "gold", 0) or 0

    # Бронза → Серебро
    if bronze >= CONVERSION:
        extra = bronze // CONVERSION
        silver = silver + extra
        bronze = bronze % CONVERSION

    # Серебро → Золото
    if silver >= CONVERSION:
        extra = silver // CONVERSION
        gold = gold + extra
        silver = silver % CONVERSION

    p.bronze = bronze
    p.silver = silver
    p.gold = gold

def total_in_bronze(p):
    """Общая стоимость в бронзе."""
    b = getattr(p, "bronze", 0) or 0
    s = getattr(p, "silver", 0) or 0
    g = getattr(p, "gold", 0) or 0
    return b + s * CONVERSION + g * CONVERSION * CONVERSION

def add_currency(p, bronze=0, silver=0, gold=0):
    """Добавить валюту с автоконвертацией."""
    if not hasattr(p, "bronze"):
        p.gold = (getattr(p, "gold", 0) or 0) + gold
        return
    p.bronze = (getattr(p, "bronze", 0) or 0) + bronze
    p.silver = (getattr(p, "silver", 0) or 0) + silver
    p.gold = (getattr(p, "gold", 0) or 0) + gold
    normalize_currencies(p)

def currency_str(p):
    """Красивая строка: 87🟤 12⚪ 3🟡"""
    b = getattr(p, "bronze", 0) or 0
    s = getattr(p, "silver", 0) or 0
    g = getattr(p, "gold", 0) or 0
    return f"{b}🟤 {s}⚪ {g}🟡"

def deduct_currency(p, cost_bronze):
    """Вычитает стоимость в бронзе из баланса игрока с учетом трех валют."""
    if cost_bronze <= 0:
        return True
    if not hasattr(p, "bronze"):
        current_gold = getattr(p, "gold", 0) or 0
        if current_gold >= cost_bronze:
            p.gold = current_gold - cost_bronze
            return True
        return False
    total = total_in_bronze(p)
    if total < cost_bronze:
        return False
    new_total = total - cost_bronze
    p.gold = new_total // (CONVERSION * CONVERSION)
    remainder = new_total % (CONVERSION * CONVERSION)
    p.silver = remainder // CONVERSION
    p.bronze = remainder % CONVERSION
    return True

def get_conversion_rate():
    """Текущий курс (для админки)."""
    return CONVERSION

