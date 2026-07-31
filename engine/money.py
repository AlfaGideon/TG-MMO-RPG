"""Деньги мира: бронза, серебро, золото и премиум-валюта.

Одна монета — одна цифра. Кошелёк героя хранится **в бронзе**
(`Player.gold` — исторически то же поле), а разряды считаются на лету:

    1 🥈 серебряная  = 100 🥉 бронзовых
    1 🥇 золотая     = 100 🥈 серебряных = 10 000 🥉 бронзовых

Так сделано намеренно: хранить три отдельных счётчика — значит вечно
ловить рассинхрон («99 серебра + 1 серебро = 100 серебра, а не 1 золото»)
и переписывать каждое место, где начисляется награда. Разряды нужны
только глазам игрока, поэтому живут в форматировании.

💎 **Премиум** (`Player.premium`) — отдельная донатная валюта. Она никогда
не смешивается с монетами: её нельзя выбить из моба, потерять в могиле
или получить за квест. Обменять 💎 на монеты можно (курс правится в
панели), обратно — нет, иначе появился бы способ «вывести донат».
"""

# ── разряды ─────────────────────────────────────────────────

BRONZE_PER_SILVER = 100
SILVER_PER_GOLD = 100
BRONZE_PER_GOLD = BRONZE_PER_SILVER * SILVER_PER_GOLD    # 10 000

GOLD_ICON, SILVER_ICON, BRONZE_ICON = "🥇", "🥈", "🥉"
PREMIUM_ICON = "💎"
PREMIUM_NAME = "кристалл Теней"

# Разряды от старшего к младшему: (номинал в бронзе, иконка, название)
COINS = [
    (BRONZE_PER_GOLD, GOLD_ICON, "золото"),
    (BRONZE_PER_SILVER, SILVER_ICON, "серебро"),
    (1, BRONZE_ICON, "бронза"),
]

# Сколько бронзы даёт один кристалл при обмене. Правится из панели.
PREMIUM_RATE = 2500

TUNABLES = {
    "premium_rate": (PREMIUM_RATE, "💎 Курс кристалла",
                     "сколько бронзы даёт один кристалл при обмене"),
    "premium_welcome": (0, "💎 Кристаллов новичку",
                        "сколько кристаллов получает герой при создании"),
}


def tune(store, key):
    """Настройка из панели или значение по умолчанию."""
    default = TUNABLES[key][0]
    if store is None:
        return default
    raw = store.settings.get(key)
    if raw is None or raw == "":
        return default
    try:
        return max(0, int(float(raw)))
    except (TypeError, ValueError):
        return default


def set_tunables(store, values):
    """Сохранить настройки валют. Пустое значение — вернуть умолчание."""
    for key in TUNABLES:
        if key not in values:
            continue
        raw = values[key]
        if raw is None or str(raw).strip() == "":
            store.settings.pop(key, None)
            continue
        try:
            store.settings[key] = max(0, int(float(raw)))
        except (TypeError, ValueError):
            continue
    store.save()
    return {k: tune(store, k) for k in TUNABLES}


# ── разбор и запись сумм ────────────────────────────────────

def split(amount):
    """Сумму в бронзе — по разрядам: (золото, серебро, бронза)."""
    amount = max(0, int(amount or 0))
    g, rest = divmod(amount, BRONZE_PER_GOLD)
    s, b = divmod(rest, BRONZE_PER_SILVER)
    return g, s, b


def total(gold=0, silver=0, bronze=0):
    """Собрать сумму в бронзе из разрядов."""
    return (int(gold) * BRONZE_PER_GOLD + int(silver) * BRONZE_PER_SILVER
            + int(bronze))


def fmt(amount):
    """Полная запись: «1🥇 23🥈 45🥉». Нулевые старшие разряды опускаются."""
    amount = int(amount or 0)
    sign = "−" if amount < 0 else ""
    g, s, b = split(abs(amount))
    parts = []
    if g:
        parts.append(f"{g}{GOLD_ICON}")
    if s or (g and b):
        parts.append(f"{s}{SILVER_ICON}")
    if b or not parts:
        parts.append(f"{b}{BRONZE_ICON}")
    return sign + " ".join(parts)


def short(amount):
    """Короткая запись одним разрядом: «1🥇», «23🥈», «45🥉»."""
    amount = int(amount or 0)
    sign = "−" if amount < 0 else ""
    value = abs(amount)
    for nominal, icon, _name in COINS:
        if value >= nominal:
            return f"{sign}{value // nominal}{icon}"
    return f"{sign}0{BRONZE_ICON}"


def plus(amount):
    """Прибавка для журналов боя: «+45🥉»."""
    amount = int(amount or 0)
    return ("+" if amount >= 0 else "") + fmt(amount)


def coin_line():
    """Строка-справка о разрядах — для помощи в боте и подсказок панели."""
    return (f"{BRONZE_ICON} бронза · {BRONZE_PER_SILVER}{BRONZE_ICON} = 1{SILVER_ICON} "
            f"серебро · {SILVER_PER_GOLD}{SILVER_ICON} = 1{GOLD_ICON} золото")


# ── кошелёк ─────────────────────────────────────────────────

def balance(p):
    """Монеты героя в бронзе."""
    return max(0, int(getattr(p, "gold", 0) or 0))


def wallet(p):
    """Строка кошелька: монеты и кристаллы."""
    gems = premium(p)
    line = fmt(balance(p))
    return f"{line} · {gems}{PREMIUM_ICON}" if gems else line


def earn(p, amount):
    """Начислить монеты. Возвращает начисленное."""
    amount = max(0, int(amount or 0))
    p.gold = balance(p) + amount
    return amount


def can_pay(p, price):
    return balance(p) >= max(0, int(price or 0))


def pay(p, price):
    """Списать монеты. False — не хватило, кошелёк не тронут."""
    price = max(0, int(price or 0))
    if balance(p) < price:
        return False
    p.gold = balance(p) - price
    return True


def lack(p, price):
    """Сколько не хватает до цены (0 — хватает)."""
    return max(0, int(price or 0) - balance(p))


# ── премиум ─────────────────────────────────────────────────

def premium(p):
    return max(0, int(getattr(p, "premium", 0) or 0))


def grant_premium(p, amount):
    """Начислить или списать кристаллы; ниже нуля не уходим."""
    p.premium = max(0, premium(p) + int(amount or 0))
    return p.premium


def spend_premium(p, amount):
    """Списать кристаллы. False — не хватило."""
    amount = max(0, int(amount or 0))
    if premium(p) < amount:
        return False
    p.premium = premium(p) - amount
    return True


def exchange(p, gems, store=None):
    """Обменять кристаллы на монеты по курсу панели.

    Обратного обмена нет намеренно: иначе донат превращался бы в
    двусторонний вывод, а внутриигровая экономика — в его придаток.
    """
    gems = int(gems or 0)
    if gems <= 0:
        return False, "Укажи, сколько кристаллов менять."
    if premium(p) < gems:
        return False, f"Не хватает {gems - premium(p)}{PREMIUM_ICON}."
    rate = tune(store, "premium_rate")
    if rate <= 0:
        return False, "Обмен кристаллов сейчас закрыт."
    spend_premium(p, gems)
    got = earn(p, gems * rate)
    return True, f"Обменяно {gems}{PREMIUM_ICON} → {fmt(got)}"


# ── экраны бота ─────────────────────────────────────────────

# Порции обмена: сколько кристаллов меняем за раз.
EXCHANGE_STEPS = (1, 5, 10, 50)


def purse(store, p):
    """Экран кошелька: разряды монет, кристаллы и обмен."""
    from engine.models import Reply

    g, s, b = split(balance(p))
    gems = premium(p)
    rate = tune(store, "premium_rate")
    lines = [
        "👛 <b>Кошелёк</b>", "",
        f"{GOLD_ICON} Золотых: <b>{g}</b>",
        f"{SILVER_ICON} Серебряных: <b>{s}</b>",
        f"{BRONZE_ICON} Бронзовых: <b>{b}</b>",
        "",
        f"{PREMIUM_ICON} {PREMIUM_NAME.capitalize()}: <b>{gems}</b>",
        "",
        f"<i>{coin_line()}</i>",
    ]
    rows = []
    if rate > 0:
        lines.append(f"<i>Обмен: 1{PREMIUM_ICON} = {fmt(rate)}</i>")
        row = [(f"{n}{PREMIUM_ICON}→", f"gemx:{n}")
               for n in EXCHANGE_STEPS if gems >= n]
        if row:
            rows.append(row)
    else:
        lines.append("<i>Обмен кристаллов закрыт.</i>")
    rows.append([("🧙 Профиль", "profile"), ("◀️ Меню", "menu")])
    return Reply(text="\n".join(lines), keyboard=rows)


def purse_exchange(store, p, arg):
    """Обменять кристаллы на монеты и вернуться на экран кошелька."""
    ok, msg = exchange(p, arg, store)
    if hasattr(store, "save_player") and ok:
        store.save_player(p)
    r = purse(store, p)
    r.alert = msg
    return r
