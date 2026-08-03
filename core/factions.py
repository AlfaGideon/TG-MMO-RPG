"""Фракции и репутация для серверного стека — паритет с engine/factions.py.

Правила и числа не дублируются, а берутся из `engine.factions`: там же
живут названия сил, вражда, звания и таблица поступков. Здесь только то,
чего в чистом движке быть не может — работа с БД.

Репутация лежит в `Character.reputation` как JSON {"guard": 12, ...}.
"""
import json

from sqlalchemy import select

from engine import factions as F
from core.models import Character

# Реэкспорт, чтобы вызывающему коду не нужно было знать про engine.
FACTIONS = F.FACTIONS
ORDER = F.ORDER
RIVALS = F.RIVALS
MIN_REP, MAX_REP = F.MIN_REP, F.MAX_REP
hostile = F.hostile


def load(character) -> dict:
    """Репутация героя. Пустое поле — все нули."""
    raw = getattr(character, "reputation", "") or ""
    try:
        data = json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        data = {}
    return {key: int(data.get(key, 0)) for key in FACTIONS}


def save(character, rep: dict) -> None:
    character.reputation = json.dumps(
        {k: int(v) for k, v in rep.items()}, ensure_ascii=False)


def value(character, key) -> int:
    return load(character).get(key, 0)


def rank(points):
    return F.rank(points)


def standing(character, key):
    return F.rank(value(character, key))


def allegiance(character):
    """Сторона героя или None. Правило то же, что в браузерном стеке."""
    rep = load(character)
    best = max(rep, key=lambda k: rep[k])
    return best if rep[best] >= 30 else None


# ── динамический стартовый бонус ────────────────────────────

# Базовые стартовые деньги каждой фракции (до балансировки населённости).
# У Гильдии больше — это её фирменный бонус за меньшие статы.
START_MONEY = {
    "guard": 100,
    "scavengers": 200,
    "cult": 100,
    "order": 100,
}

# Границы множителя: малочисленная фракция доплачивает новичкам до ×2,
# перенаселённая урезает выдачу до ×0.5 — так стартовый выбор сам
# балансирует количество игроков во фракциях.
START_BONUS_MIN = 0.5
START_BONUS_MAX = 2.0


async def faction_population(session) -> dict:
    """Сколько героев присягнуло каждой фракции (по стартовому выбору).

    Старые герои без колонки `faction` восстанавливаются по стартовой
    репутации (allegiance). Герои, не завершившие создание
    (пустая репутация), никому не принадлежат и не считаются.
    """
    counts = {key: 0 for key in FACTIONS}
    result = await session.execute(
        select(Character.faction, Character.reputation))
    for stored, reputation in result.all():
        key = stored if stored in counts else None
        if key is None and reputation:
            try:
                data = json.loads(reputation)
            except (ValueError, TypeError):
                data = {}
            if data:
                best = max(data, key=lambda k: data[k])
                if best in counts and data[best] >= 30:
                    key = best
        if key in counts:
            counts[key] += 1
    return counts


def start_bonus_mult(counts: dict, faction_key) -> float:
    """Множитель стартовой награды фракции по её населённости.

    Сглаживание по Лапласу (виртуальный житель в каждой фракции): на
    пустом сервере все множители ровно 1.0; чем фракция меньше среднего,
    тем жирнее бонус (до START_BONUS_MAX), чем больше — тем скуднее
    выдача (до START_BONUS_MIN).
    """
    total = sum(counts.get(k, 0) for k in FACTIONS)
    avg = (total + len(FACTIONS)) / len(FACTIONS)
    mine = counts.get(faction_key, 0) + 1
    mult = avg / mine if mine else START_BONUS_MAX
    return max(START_BONUS_MIN, min(START_BONUS_MAX, mult))


async def start_bonus(session, faction_key, base: int | None = None) -> dict:
    """Итог стартовой выдачи фракции: {'base', 'count', 'mult', 'bronze'}.

    Округление до десятков — красивые числа; минимум 10 бронзы, чтобы
    старт никогда не был совсем пустым.
    """
    counts = await faction_population(session)
    base = base if base is not None else START_MONEY.get(faction_key, 100)
    mult = start_bonus_mult(counts, faction_key)
    bronze = max(10, int(round((base * mult) / 10.0)) * 10)
    return {
        "base": base,
        "count": counts.get(faction_key, 0),
        "mult": mult,
        "bronze": bronze,
    }


# ── начисление ──────────────────────────────────────────────

def award(character, deed, scale=1):
    """Записать поступок. Возвращает строки-уведомления.

    Логика повторяет engine.factions.award: помощь одной силе злит её
    соперника, поэтому своим для всех стать нельзя.
    """
    table = F.DEEDS.get(deed)
    if not table:
        return []
    rep = load(character)
    moved = {}
    for key, delta in table.items():
        step = int(delta * scale)
        if not step:
            continue
        moved[key] = moved.get(key, 0) + step
        if step > 0:
            foe = RIVALS.get(key)
            if foe:
                moved[foe] = moved.get(foe, 0) - max(1, int(step * F.SPITE))

    lines = []
    for key, step in moved.items():
        before = rep.get(key, 0)
        rep[key] = max(MIN_REP, min(MAX_REP, before + step))
        if rep[key] == before:
            continue
        icon = FACTIONS[key][0]
        sign = "+" if step > 0 else ""
        _, was_title = F.rank(before)
        now_icon, now_title = F.rank(rep[key])
        note = f"{icon} {FACTIONS[key][1]}: {sign}{step}"
        if now_title != was_title:
            note += f" → {now_icon} <b>{now_title}</b>"
        lines.append(note)
    if lines:
        save(character, rep)
    return lines


def award_for_mob(character, mob):
    """Репутация за убитую тварь: нежить ценят одни, зверьё — другие."""
    name = (getattr(mob, "name", "") or "").lower()
    deed = "undead_slain" if any(w in name for w in F.UNDEAD) else "beast_slain"
    return award(character, deed)


# ── что даёт репутация ──────────────────────────────────────

def discount(character) -> float:
    """Скидка у торговцев: начинается со звания «Знакомый»."""
    best = max(load(character).values() or [0])
    if best < F.DISCOUNT_FROM:
        return 0.0
    span = MAX_REP - F.DISCOUNT_FROM
    grown = (best - F.DISCOUNT_FROM) / span if span > 0 else 1.0
    return round(min(F.SHOP_DISCOUNT, F.SHOP_DISCOUNT * grown), 3)


def price_for(character, base_price: int) -> int:
    """Цена товара с учётом репутации — единая точка для витрины и покупки."""
    return max(1, int(base_price * (1.0 - discount(character))))


async def cataclysm_mult(session) -> float:
    """Настроения игроков ускоряют или замедляют бедствия."""
    result = await session.execute(select(Character))
    cult = guard = 0
    for ch in result.scalars().all():
        rep = load(ch)
        cult += max(0, rep.get("cult", 0))
        guard += max(0, rep.get("guard", 0))
    if not cult and not guard:
        return 1.0
    if cult > guard * 1.5:
        return F.CULT_CATACLYSM
    if guard > cult * 1.5:
        return F.GUARD_CATACLYSM
    return 1.0


# ── реакция жителей ─────────────────────────────────────────

def npc_faction(npc_name: str, npc_type: str = ""):
    """К какой силе принадлежит житель — по имени и роду занятий."""
    name = npc_name or ""
    if "Скупщик" in name or "Наёмник" in name:
        return "scavengers"
    if "Гробовщик" in name or "Летописец" in name:
        return "cult"
    return "guard"


def refuses(character, npc_name: str, npc_type: str = "") -> bool:
    """Откажется ли житель иметь дело: враждебность имеет цену."""
    key = npc_faction(npc_name, npc_type)
    return value(character, key) <= -100


def greeting(character, npc_name: str, npc_type: str = "") -> str:
    """Как житель здоровается — по репутации героя."""
    key = npc_faction(npc_name, npc_type)
    points = value(character, key)
    icon, title = F.rank(points)
    if points >= 80:
        mood = "Тебе здесь рады."
    elif points >= 30:
        mood = "Тебя узнают."
    elif points <= -100:
        mood = "Тебе здесь не рады."
    elif points <= -30:
        mood = "На тебя смотрят косо."
    else:
        mood = "Тебя не знают."
    return f"\n\n{FACTIONS[key][0]} <i>{FACTIONS[key][1]}: {icon} {title}. {mood}</i>"


def card_text(character) -> str:
    """Экран репутации для бота."""
    rep = load(character)
    lines = ["🧭 <b>Репутация</b>", ""]
    for key in ORDER:
        icon, name, motto, _foe = FACTIONS[key]
        points = rep.get(key, 0)
        r_icon, r_title = F.rank(points)
        lines.append(f"{icon} <b>{name}</b> — {r_icon} {r_title} ({points})")
        lines.append(F._bar(points))
        lines.append(f"<i>{motto}</i>")
        lines.append("")
    side = allegiance(character)
    if side:
        lines.append(f"⚔️ Твоя сторона: {FACTIONS[side][0]} <b>{FACTIONS[side][1]}</b>")
        lines.append(f"<i>Соперник — {FACTIONS[RIVALS[side]][1]}.</i>")
    else:
        lines.append("<i>Ты пока никому не свой. Помогай — и тебя заметят.</i>")
    disc = discount(character)
    if disc:
        lines.append(f"💵 Скидка в лавке: <b>{int(disc * 100)}%</b>")
    lines.append("\n<i>Помощь одной силе злит противоположную — выбирай.</i>")
    return "\n".join(lines)
