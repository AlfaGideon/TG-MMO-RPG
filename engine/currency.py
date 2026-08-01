"""Трёхвалютная система: бронза → серебро → золото (1:100)"""

CONVERSION = 100  # 1 серебро = 100 бронзы, 1 золото = 100 серебра

def normalize_currencies(p):
    """Приводит валюты к каноническому виду (не больше 99 в младшей)."""
    if not hasattr(p, "bronze"):
        return

    # Бронза → Серебро
    if getattr(p, "bronze", 0) >= CONVERSION:
        extra = p.bronze // CONVERSION
        p.silver = getattr(p, "silver", 0) + extra
        p.bronze = p.bronze % CONVERSION

    # Серебро → Золото
    if getattr(p, "silver", 0) >= CONVERSION:
        extra = p.silver // CONVERSION
        p.gold = getattr(p, "gold", 0) + extra
        p.silver = p.silver % CONVERSION

def total_in_bronze(p):
    """Общая стоимость в бронзе."""
    b = getattr(p, "bronze", 0)
    s = getattr(p, "silver", 0)
    g = getattr(p, "gold", 0)
    return b + s * CONVERSION + g * CONVERSION * CONVERSION

def add_currency(p, bronze=0, silver=0, gold=0):
    """Добавить валюту с автоконвертацией."""
    if not hasattr(p, "bronze"):
        p.gold = getattr(p, "gold", 0) + gold
        return
    p.bronze = getattr(p, "bronze", 0) + bronze
    p.silver = getattr(p, "silver", 0) + silver
    p.gold = getattr(p, "gold", 0) + gold
    normalize_currencies(p)

def currency_str(p):
    """Красивая строка: 87🪙 12🥈 3🪙"""
    b = getattr(p, "bronze", 0)
    s = getattr(p, "silver", 0)
    g = getattr(p, "gold", 0)
    return f"{b}🪙 {s}🥈 {g}🪙"

def deduct_currency(p, cost_bronze):
    """Вычитает стоимость в бронзе из баланса игрока с учетом трех валют."""
    if not hasattr(p, "bronze"):
        if getattr(p, "gold", 0) >= cost_bronze:
            p.gold -= cost_bronze
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
