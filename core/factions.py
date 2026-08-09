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
    lines = ["🧭 <b>Репутация и Геополитика</b>", ""]
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


# ── ВЛИЯНИЕ ФРАКЦИЙ НА ЛОКАЦИИ (INFLUENCE MAP) ───────────────

def get_location_influence(location) -> dict:
    """Распределение очков контроля фракций в локации."""
    raw = getattr(location, "influence_json", "") or ""
    try:
        data = json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        data = {}
    return {k: int(data.get(k, 25)) for k in ORDER}


def save_location_influence(location, influence: dict) -> None:
    location.influence_json = json.dumps(
        {k: int(v) for k, v in influence.items() if k in ORDER},
        ensure_ascii=False
    )


async def add_location_influence(session, location, faction_key: str, points: int = 5) -> dict:
    """Увеличивает влияние фракции в регионе за совершённые подвиги."""
    if not faction_key or faction_key not in ORDER or location is None:
        return {}
    inf = get_location_influence(location)
    inf[faction_key] = inf.get(faction_key, 0) + points
    save_location_influence(location, inf)
    await session.flush()
    return inf


def get_dominant_faction(location) -> tuple[str | None, int]:
    """Определяет доминирующую фракцию и процент её контроля."""
    inf = get_location_influence(location)
    total = sum(inf.values()) or 1
    best_faction = max(inf, key=lambda k: inf[k])
    pct = int((inf[best_faction] / total) * 100)
    if pct <= 28:
        return None, pct  # Паритет сил
    return best_faction, pct


def location_influence_text(location) -> str:
    """Текстовая полоса геополитического контроля для экрана локации."""
    inf = get_location_influence(location)
    total = sum(inf.values()) or 1
    parts = []
    for k in ORDER:
        pct = int((inf[k] / total) * 100)
        icon = FACTIONS[k][0]
        parts.append(f"{icon} {pct}%")
    dom, dom_pct = get_dominant_faction(location)
    dom_str = f"👑 Контроль: <b>{FACTIONS[dom][1]}</b> ({dom_pct}%)" if dom else "⚖️ Баланс сил"
    return f"{dom_str}\n" + " | ".join(parts)


from datetime import datetime, timedelta, timezone
from core.models import FactionOutpost, FactionDecree, Cell


def _now():
    return datetime.now(timezone.utc)


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def get_outposts(session) -> list[FactionOutpost]:
    """Список всех пограничных аванпостов мира."""
    result = await session.execute(
        select(FactionOutpost).order_by(FactionOutpost.id)
    )
    return result.scalars().all()


async def get_outpost_at_cell(session, cell_id: int) -> FactionOutpost | None:
    """Аванпост на конкретной клетке мира."""
    result = await session.execute(
        select(FactionOutpost).where(FactionOutpost.cell_id == cell_id)
    )
    return result.scalar_one_or_none()


async def faction_outpost_bonuses(session, faction_key: str) -> dict:
    """Глобальные бонусы, которые фракция получает от захваченных аванпостов."""
    if not faction_key:
        return {"outposts_count": 0, "damage_pct": 0, "defense_pct": 0, "exp_pct": 0, "gold_pct": 0}

    result = await session.execute(
        select(FactionOutpost).where(FactionOutpost.controlling_faction == faction_key)
    )
    outposts = result.scalars().all()
    count = len(outposts)
    return {
        "outposts_count": count,
        "damage_pct": count * 5,    # +5% урона за каждый удерживаемый форт
        "defense_pct": count * 4,   # +4% защиты за форт
        "exp_pct": count * 6,       # +6% опыта за форт
        "gold_pct": count * 5,      # +5% золота за форт
    }


async def attack_outpost(session, character, outpost: FactionOutpost, damage: int) -> dict:
    """Атака аванпоста для ослабления и перехвата контроля."""
    my_f = allegiance(character)
    if not my_f:
        return {"ok": False, "reason": "Чтобы захватывать аванпосты, присягни одной из фракций!"}
    if outpost.controlling_faction == my_f:
        # Ремонт своего аванпоста
        heal = min(outpost.max_defense_hp - outpost.defense_hp, max(10, damage))
        if heal <= 0:
            return {"ok": False, "reason": "Аванпост твоей фракции уже укреплён на максимум!"}
        outpost.defense_hp += heal
        await session.flush()
        return {"ok": True, "repaired": True, "amount": heal, "current": outpost.defense_hp}

    # Нанесение урона укреплениям вражеского аванпоста
    dmg = max(5, damage)
    outpost.defense_hp -= dmg
    captured = False
    if outpost.defense_hp <= 0:
        outpost.controlling_faction = my_f
        outpost.defense_hp = outpost.max_defense_hp // 2
        outpost.last_captured_at = _now()
        captured = True
        award(character, "boss_slain", scale=1.5)  # Большая награда за взятие крепости

    await session.flush()
    return {
        "ok": True,
        "captured": captured,
        "damage": dmg,
        "remaining_hp": max(0, outpost.defense_hp),
        "faction": my_f,
    }


# ── КАЗНА ФРАКЦИИ И УКАЗЫ ЛИДЕРА ────────────────────────────

DECREES = {
    "militarization": {
        "name": "⚔️ Милитаризация",
        "desc": "+15% к урону всей фракции во всех битвах",
        "cost": 1000,
        "damage_mult": 1.15,
        "defense_mult": 1.0,
        "gold_mult": 1.0,
        "exp_mult": 1.0,
    },
    "trade_boom": {
        "name": "💰 Торговый бум",
        "desc": "+20% золота и трофеев со всех побед и сундуков",
        "cost": 1200,
        "damage_mult": 1.0,
        "defense_mult": 1.0,
        "gold_mult": 1.20,
        "exp_mult": 1.0,
    },
    "citadel": {
        "name": "🛡 Неприступная цитадель",
        "desc": "+15% к броне и защите от ран",
        "cost": 1000,
        "damage_mult": 1.0,
        "defense_mult": 1.15,
        "gold_mult": 1.0,
        "exp_mult": 1.0,
    },
    "knowledge": {
        "name": "🔮 Тайные знания",
        "desc": "+25% к опыту при исследовании мира и битвах",
        "cost": 1500,
        "damage_mult": 1.0,
        "defense_mult": 1.0,
        "gold_mult": 1.0,
        "exp_mult": 1.25,
    },
}


async def get_or_create_decree(session, faction_key: str) -> FactionDecree:
    result = await session.execute(
        select(FactionDecree).where(FactionDecree.faction == faction_key)
    )
    dec = result.scalar_one_or_none()
    if dec is None:
        dec = FactionDecree(faction=faction_key, treasury_bronze=500, active_decree="none")
        session.add(dec)
        await session.flush()
    return dec


async def active_decree_bonuses(session, faction_key: str) -> dict:
    """Множители от активного указа лидера фракции."""
    if not faction_key:
        return {"damage_mult": 1.0, "defense_mult": 1.0, "gold_mult": 1.0, "exp_mult": 1.0, "name": "Нет"}
    dec = await get_or_create_decree(session, faction_key)
    if not dec.active_decree or dec.active_decree == "none":
        return {"damage_mult": 1.0, "defense_mult": 1.0, "gold_mult": 1.0, "exp_mult": 1.0, "name": "Нет"}

    until = _aware(dec.active_until)
    if until and _now() > until:
        dec.active_decree = "none"
        await session.flush()
        return {"damage_mult": 1.0, "defense_mult": 1.0, "gold_mult": 1.0, "exp_mult": 1.0, "name": "Истёк"}

    row = DECREES.get(dec.active_decree, {})
    return {
        "damage_mult": row.get("damage_mult", 1.0),
        "defense_mult": row.get("defense_mult", 1.0),
        "gold_mult": row.get("gold_mult", 1.0),
        "exp_mult": row.get("exp_mult", 1.0),
        "name": row.get("name", dec.active_decree),
    }


async def donate_treasury(session, character, faction_key: str, bronze: int) -> dict:
    """Пожертвование в казну фракции."""
    from engine.currency import total_in_bronze, deduct_currency
    if bronze <= 0:
        return {"ok": False, "reason": "Сумма должна быть больше нуля."}
    if total_in_bronze(character) < bronze:
        return {"ok": False, "reason": f"Не хватает {bronze - total_in_bronze(character)}🟤."}

    deduct_currency(character, bronze)
    dec = await get_or_create_decree(session, faction_key)
    dec.treasury_bronze = (dec.treasury_bronze or 0) + bronze

    # Награда репутацией за щедрость
    award(character, "undead_slain", scale=max(1, bronze // 100))
    await session.flush()
    return {"ok": True, "donated": bronze, "treasury": dec.treasury_bronze}


async def enact_decree(session, character, faction_key: str, decree_key: str, hours: int = 12) -> dict:
    """Лидер издаёт указ, расходуя казну."""
    if decree_key not in DECREES:
        return {"ok": False, "reason": "Неизвестный указ."}
    dec = await get_or_create_decree(session, faction_key)
    cost = DECREES[decree_key]["cost"]
    if (dec.treasury_bronze or 0) < cost:
        return {"ok": False, "reason": f"В казне не хватает средств! Нужно {cost}🟤, есть {dec.treasury_bronze or 0}🟤."}

    dec.treasury_bronze -= cost
    dec.active_decree = decree_key
    dec.active_until = _now() + timedelta(hours=hours)
    dec.enacted_by_character_id = character.id
    await session.flush()
    return {"ok": True, "decree": DECREES[decree_key]["name"], "until": dec.active_until}


# ── ДИВЕРСИИ И ШПИОНАЖ В ПОДКОПАХ ───────────────────────────

async def sabotage_tunnel(session, character, target_location_id: int, sabotage_type: str) -> dict:
    """Проведение диверсии в подвалах вражеского замка."""
    from engine.currency import add_currency
    my_f = allegiance(character)
    if not my_f:
        return {"ok": False, "reason": "Для диверсий требуется принадлежность к фракции!"}

    if sabotage_type == "poison_supplies":
        award(character, "grave_looted", scale=2)
        add_currency(character, bronze=150)
        return {
            "ok": True,
            "title": "☠️ Яд в колодцах",
            "desc": "Ты скрытно отравил запасы провианта вражеского замка! Получено +150🟤 и уважение соратников.",
        }
    elif sabotage_type == "scout_alarm":
        award(character, "undead_slain", scale=2)
        add_currency(character, bronze=100)
        return {
            "ok": True,
            "title": "🔔 Сигнальные растяжки",
            "desc": "Ты установил скрытые ловушки и сигнальные колокольчики в тоннеле! Получено +100🟤.",
        }
    elif sabotage_type == "disrupt_forge":
        award(character, "boss_slain", scale=1)
        add_currency(character, bronze=200)
        return {
            "ok": True,
            "title": "🔨 Порча наковален",
            "desc": "Ты вывел из строя кузнечные меха врага и унёс ценные заготовки! Получено +200🟤.",
        }
    return {"ok": False, "reason": "Неизвестный тип диверсии."}


# ── КОНТРАБАНДНЫЕ КАРАВАНЫ ──────────────────────────────────

async def caravan_action(session, character, caravan_event, action: str) -> dict:
    """Сопровождение или нападение на торговый караван."""
    from engine.currency import add_currency
    my_f = allegiance(character)
    if action == "escort":
        # Стража / Орден защищают
        gold = 250
        exp = 300
        add_currency(character, bronze=gold)
        character.experience = (character.experience or 0) + exp
        award(character, "undead_slain", scale=3)
        return {
            "ok": True,
            "title": "🛡 Обоз успешно сопровождён",
            "desc": f"Ты отбил нападение разбойников и доставил купцов в целости!\nНаграда: +{gold}🟤 | +{exp}⭐ опыта.",
        }
    elif action == "ambush":
        # Падальщики / Культ грабят
        gold = 400
        exp = 150
        add_currency(character, bronze=gold)
        character.experience = (character.experience or 0) + exp
        award(character, "grave_looted", scale=3)
        return {
            "ok": True,
            "title": "⚔️ Караван разграблен",
            "desc": f"Ты перебил охрану каравана и вскрыл сундуки с контрабандой!\nДобыча: +{gold}🟤 | +{exp}⭐ опыта.",
        }
    return {"ok": False, "reason": "Неизвестное действие с караваном."}

