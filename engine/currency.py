"""Трёхвалютная система: бронза → серебро → золото (1:100).

**Семантика (важно).** Любая внутриигровая сумма в движке считается
в бронзе — как и на сервере (`Item.price`, награды мобов, стартовый бонус
фракции 100–200🟤). Цены в `engine/data.ITEMS` (20…180) и стартовые деньги
героя по масштабу совпадали именно с бронзой, поэтому переход не меняет
баланс: те же числа, просто теперь они честно называются бронзой и
конвертируются в серебро и золото при накоплении.

Работать с кошельком следует через `total`/`earn`/`spend`/`fmt` —
прямые `p.gold += N` обходят конвертацию и ломают отображение.
"""

CONVERSION = 100  # 1 серебро = 100 бронзы, 1 золото = 100 серебра

# Версия формата кошелька. 0/отсутствует — старый сейв, где всё лежало
# в поле gold как «монеты»; 2 — трёхвалютный кошелёк.
WALLET_VERSION = 2

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



# ── единая точка работы с кошельком ─────────────────────────

def total(p) -> int:
    """Всё богатство героя в бронзе — этим меряются любые цены."""
    return total_in_bronze(p)


def earn(p, bronze: int) -> int:
    """Начислить сумму в бронзе с автоконвертацией. Возвращает новый итог."""
    add_currency(p, bronze=int(bronze))
    return total(p)


def spend(p, bronze: int) -> bool:
    """Списать сумму в бронзе. False — не хватило, кошелёк не тронут."""
    return deduct_currency(p, int(bronze))


def can_afford(p, bronze: int) -> bool:
    return total(p) >= int(bronze)


def fmt(p) -> str:
    """Кошелёк строкой: «87🟤 12⚪ 3🟡»."""
    return currency_str(p)


def short(bronze: int) -> str:
    """Цена одной строкой: мелочь в бронзе, крупные суммы — с разрядами.

    Показывать 12500🟤 бессмысленно, но и дробить каждую цену на три
    значка — шумно, поэтому крупное отображается как «1🟡 25⚪».
    """
    bronze = int(bronze)
    if bronze < CONVERSION:
        return f"{bronze}🟤"
    gold, rest = divmod(bronze, CONVERSION * CONVERSION)
    silver, copper = divmod(rest, CONVERSION)
    parts = []
    if gold:
        parts.append(f"{gold}🟡")
    if silver:
        parts.append(f"{silver}⚪")
    if copper and not gold:          # при золоте мелочь уже не важна
        parts.append(f"{copper}🟤")
    return " ".join(parts) or "0🟤"


def migrate_raw(raw: dict) -> dict:
    """Починить сырой словарь сохранения до создания Player.

    Раньше всё богатство лежало в `gold` и означало «монеты» того же
    масштаба, что нынешняя бронза. Переносим сумму в бронзу, чтобы
    покупательная способность не изменилась ни на монету: 300 «золота»
    старого сейва — это 300🟤, то есть 3⚪ после нормализации.

    Идемпотентно: сейвы с `wallet_v >= 2` не трогаются.
    """
    if not isinstance(raw, dict):
        return raw
    if int(raw.get("wallet_v") or 0) >= WALLET_VERSION:
        return raw
    raw["bronze"] = int(raw.get("gold") or 0) + int(raw.get("bronze") or 0)
    raw["silver"] = int(raw.get("silver") or 0)
    raw["gold"] = 0
    raw["wallet_v"] = WALLET_VERSION
    return raw
