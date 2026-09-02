"""Катаклизмы и мировые боссы для серверного стека.

Паритет с `engine/cataclysm.py` и `engine/worldboss.py`: каталоги бедствий
и боссов берутся оттуда же, поэтому числа и описания одинаковы в обоих
стеках по построению, а не по совпадению.

Оба вида событий живут в одной таблице `WorldEvent` — у них общая природа:
срок, вести игрокам, летопись. Различает поле `kind`.

Слепок клеток (`snapshot`) позволяет вернуть мир как было: бедствие правит
рельеф, а когда стихает — всё восстанавливается, кроме убитых тварей.
"""
import json
import random
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from engine.cataclysm_kinds import KINDS, MOB_MULT, ORDER  # noqa: F401
from engine.worldboss import BOSSES, MIN_SHARE, PHASE_AT
from engine.worldboss import ORDER as BOSS_ORDER
from core.models import Cell, Character, Location, WorldEvent, WorldEventDamage


def _now():
    return datetime.now(timezone.utc)


def _aware(dt):
    """SQLite возвращает naive-время — приводим к сравнимому виду."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def title(kind, key):
    table = KINDS if kind == "cataclysm" else BOSSES
    row = table.get(key) or {}
    return f"{row.get('icon', '❓')} {row.get('name', key)}"


# ── катаклизмы ──────────────────────────────────────────────

async def active_cataclysms(session, location_id=None):
    """Живые бедствия. Просроченные снимаются сами."""
    await sweep(session)
    # location подгружаем сразу: шаблоны панели рендерятся вне сессии,
    # а локальное бедствие без имени места выглядит поломанным.
    q = select(WorldEvent).where(WorldEvent.kind == "cataclysm") \
                          .options(selectinload(WorldEvent.location)) \
                          .where(WorldEvent.is_active == True)
    result = await session.execute(q)
    events = result.scalars().all()
    if location_id is None:
        return events
    return [e for e in events
            if e.is_global or e.location_id == int(location_id)]


async def effects(session, location_id):
    """Множители правил для локации — как в engine.cataclysm.effects."""
    eff = {"mob_rate": 1.0, "damage": 1.0, "loot": 1.0, "gold": 1.0, "rest": 1.0}
    worst = {"ambush": 0.0, "join": 0.0}
    for ev in await active_cataclysms(session, location_id):
        k = KINDS.get(ev.key) or {}
        for key in eff:
            eff[key] *= float(k.get(key, 1.0))
        for key in worst:
            worst[key] = max(worst[key], float(k.get(key, 0.0)))
    eff.update(worst)
    return eff


async def strike(session, key, location_id=None, hours=None):
    """Обрушить бедствие. Клетки правятся со слепком."""
    k = KINDS.get(key)
    if not k:
        raise ValueError("Неизвестный катаклизм")
    is_global = location_id is None
    for ev in await active_cataclysms(session):
        if ev.key == key and (ev.is_global == is_global
                              and ev.location_id == location_id):
            raise ValueError(f"{title('cataclysm', key)} уже бушует здесь")

    dur = float(hours if hours is not None else k["hours"])
    ev = WorldEvent(
        kind="cataclysm", key=key, location_id=location_id,
        is_global=is_global, until=_now() + timedelta(hours=max(0.05, dur)),
        is_active=True,
    )
    session.add(ev)
    await session.flush()
    ev.cells_touched = await _apply(session, ev, k)
    await session.flush()
    return ev


async def _apply(session, ev, k):
    """Перекроить клетки локации, сохранив слепок для отката."""
    q = select(Cell).where(Cell.target_location_id.is_(None))
    if not ev.is_global:
        q = q.where(Cell.location_id == ev.location_id)
    result = await session.execute(q)
    pool = [c for c in result.scalars().all() if c.is_passable or c.tile_type != "wall"]
    random.shuffle(pool)
    take = max(1, int(len(pool) * float(k.get("spread", 0.3))))

    snap = {}
    for c in pool[:take]:
        snap[str(c.id)] = [c.tile_type, bool(c.is_passable),
                           c.mob_id, bool(c.has_chest)]
        tile = (k.get("tiles") or {}).get(c.tile_type)
        if tile:
            c.tile_type = tile
        if c.is_passable and c.tile_type != "road" and random.random() < k.get("block", 0):
            c.is_passable, c.tile_type = False, "wall"
        if c.is_passable and not c.has_chest and random.random() < k.get("chests", 0):
            c.has_chest = True
    ev.snapshot = json.dumps(snap)
    return len(snap)


async def _restore(session, ev):
    """Вернуть рельеф и сундуки. Тварей не воскрешаем — их вернёт спавн."""
    # Летопись (IDEAS-100 № 60): мир пережил этот катаклизм — веха
    # без автора. Точка одна на оба пути завершения (ручное закрытие
    # из админки и автоснятие по сроку в sweep), запись дедуплицируется
    # по ключу внутри record_server_first.
    if ev.kind == "cataclysm":
        from core.legends import record_server_first
        await record_server_first(
            session, f"cataclysm:{ev.key}",
            f"Первое пережитое бедствие: {title('cataclysm', ev.key)}")
    try:
        snap = json.loads(ev.snapshot or "{}")
    except (ValueError, TypeError):
        return
    for cell_id, row in snap.items():
        cell = await session.get(Cell, int(cell_id))
        if cell is None:
            continue
        cell.tile_type, cell.is_passable = row[0], bool(row[1])
        cell.has_chest = bool(row[3])


async def end_cataclysm(session, event_id):
    ev = await session.get(WorldEvent, int(event_id))
    if ev is None or not ev.is_active:
        return None
    await _restore(session, ev)
    ev.is_active = False
    await session.flush()
    return ev


# ── мировые боссы ───────────────────────────────────────────

async def active_boss(session):
    await sweep(session)
    result = await session.execute(
        select(WorldEvent).where(WorldEvent.kind == "boss")
                          .where(WorldEvent.is_active == True)
    )
    return result.scalars().first()


async def summon_boss(session, key, location_id=None, hours=None):
    """Призвать босса. Один на мир."""
    b = BOSSES.get(key)
    if not b:
        raise ValueError("Неизвестный босс")
    if await active_boss(session):
        raise ValueError("Мировой босс уже бродит по землям")
    if location_id is None:
        location_id = await _risky_location(session)

    dur = float(hours if hours is not None else b["hours"])
    ev = WorldEvent(
        kind="boss", key=key, location_id=location_id, is_global=False,
        hp=int(b["hp"]), max_hp=int(b["hp"]), phase=0,
        until=_now() + timedelta(hours=max(0.05, dur)), is_active=True,
    )
    session.add(ev)
    await session.flush()
    return ev


async def _risky_location(session):
    """Босс приходит в опасные земли, а не в деревню."""
    from core.enums import LocationType

    result = await session.execute(select(Location))
    locs = result.scalars().all()
    risky = [l for l in locs
             if getattr(l.location_type, "value", l.location_type) != "safe"]
    pick = random.choice(risky or locs) if locs else None
    return pick.id if pick else None


async def hit_boss(session, character, damage):
    """Записать урон. Возвращает (осталось HP, сменилась ли фаза).

    HP списывается одним атомарным UPDATE — при одновременных ударах
    урон не теряется. Награду за добивание раздаёт только тот, кто
    отщёлкнул `is_active` первым (иначе два добивших получали награду
    дважды — по разу на каждого).
    """
    from sqlalchemy import update
    ev = await active_boss(session)
    if ev is None:
        return 0, False
    dealt = max(1, int(damage))
    await session.execute(
        update(WorldEvent)
        .where(WorldEvent.id == ev.id)
        .where(WorldEvent.is_active == True)  # noqa: E712
        # MAX(0, hp - N): работает и в SQLite, и в Postgres (greatest — нет)
        .values(hp=func.max(0, WorldEvent.hp - dealt))
    )
    await session.flush()
    await session.refresh(ev, ["hp"])
    ev_hp = int(ev.hp)

    result = await session.execute(
        select(WorldEventDamage)
        .where(WorldEventDamage.event_id == ev.id)
        .where(WorldEventDamage.character_id == character.id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = WorldEventDamage(event_id=ev.id, character_id=character.id,
                               damage=dealt)
        session.add(row)
    else:
        row.damage = int(row.damage) + dealt

    phased = False
    if not ev.phase and ev_hp <= ev.max_hp * PHASE_AT:
        ev.phase = 1
        phased = True
    if ev_hp <= 0:
        # Добивший ровно один: у проигравшего гонку rowcount == 0.
        res = await session.execute(
            update(WorldEvent)
            .where(WorldEvent.id == ev.id)
            .where(WorldEvent.is_active == True)  # noqa: E712
            .values(is_active=False)
        )
        if res.rowcount == 1:
            await _reward_boss(session, ev)
            ev.is_active = False
            # Летопись (IDEAS-100 № 60): первый на сервере разгром этого
            # босса записывается на добившего — он же единственный
            # победитель гонки. Повторная запись того же ключа
            # отклоняется внутри record_server_first, поэтому «первый»
            # остаётся первым навсегда.
            from core.legends import record_server_first
            await record_server_first(
                session, f"boss:{ev.key}",
                f"Первое убийство: {title('boss', ev.key)}", character)
    await session.flush()
    return ev_hp, phased


async def _reward_boss(session, ev):
    """Награда по вкладу: золото и опыт всем, кто заметно бился."""
    result = await session.execute(
        select(WorldEventDamage).where(WorldEventDamage.event_id == ev.id)
    )
    rows = result.scalars().all()
    total = sum(int(r.damage) for r in rows) or 1
    b = BOSSES.get(ev.key) or {}
    for r in rows:
        share = int(r.damage) / total
        if share < MIN_SHARE:
            continue
        ch = await session.get(Character, r.character_id)
        if ch is None:
            continue
        from engine.currency import add_currency
        reward_bronze = max(10, int(b.get("hp", 1000) * share * 0.5))
        add_currency(ch, bronze=reward_bronze)
        ch.experience += max(10, int(b.get("hp", 1000) * share * 0.8))
        from core import factions as core_factions
        core_factions.award(ch, "boss_slain")
        # Карма: победа над боссом очищает — единая точка на всех бойцов.
        from core import karma as core_karma
        core_karma.change_karma(ch, core_karma.KILL_BOSS)


async def boss_contribution(session, ev, character) -> float:
    result = await session.execute(
        select(WorldEventDamage).where(WorldEventDamage.event_id == ev.id)
    )
    rows = result.scalars().all()
    total = sum(int(r.damage) for r in rows) or 1
    mine = next((int(r.damage) for r in rows
                 if r.character_id == character.id), 0)
    return mine / total


# ── общий срок ──────────────────────────────────────────────

async def sweep(session):
    """Снять всё, чему вышел срок. Возвращает число снятых событий."""
    result = await session.execute(
        select(WorldEvent).where(WorldEvent.is_active == True)
    )
    done = 0
    now = _now()
    for ev in result.scalars().all():
        if _aware(ev.until) and now < _aware(ev.until):
            continue
        if ev.kind == "cataclysm":
            await _restore(session, ev)
        ev.is_active = False
        done += 1
    if done:
        await session.flush()
    return done


# ── ОСАДЫ ЦИТАДЕЛЕЙ И КАРАВАНЫ ─────────────────────────────

async def active_sieges(session, location_id=None):
    """Активные осады замков."""
    await sweep(session)
    q = select(WorldEvent).where(WorldEvent.kind == "siege") \
                          .where(WorldEvent.is_active == True)
    if location_id is not None:
        q = q.where(WorldEvent.location_id == location_id)
    result = await session.execute(q)
    return result.scalars().all()


async def start_siege(session, castle_location_id: int, attacking_faction: str, hp: int = 3000, hours: float = 4.0):
    """Начать осаду цитадели вражеской фракцией."""
    ev = WorldEvent(
        kind="siege",
        key=f"siege_{attacking_faction}",
        location_id=castle_location_id,
        is_global=False,
        hp=hp,
        max_hp=hp,
        phase=0,
        until=_now() + timedelta(hours=hours),
        is_active=True,
    )
    session.add(ev)
    await session.flush()
    return ev


async def active_caravans(session, location_id=None):
    """Активные торговые караваны."""
    await sweep(session)
    q = select(WorldEvent).where(WorldEvent.kind == "caravan") \
                          .where(WorldEvent.is_active == True)
    if location_id is not None:
        q = q.where(WorldEvent.location_id == location_id)
    result = await session.execute(q)
    return result.scalars().all()


async def spawn_caravan(session, location_id: int, hours: float = 6.0):
    """Появление контрабандного каравана на тракте."""
    ev = WorldEvent(
        kind="caravan",
        key="contraband_caravan",
        location_id=location_id,
        is_global=False,
        hp=500,
        max_hp=500,
        phase=0,
        until=_now() + timedelta(hours=hours),
        is_active=True,
    )
    session.add(ev)
    await session.flush()
    return ev



# ── осады цитаделей (правила — engine/siege.py) ─────────────
# IDEAS-next, пункт 4. Раньше осада была декорацией: событие показывало
# HP ворот, но повлиять на него мог только админ, снявший событие. Теперь
# герой бьёт по воротам или чинит их — роль определяет преданность
# (engine.factions.allegiance), числа считает общий движковый модуль,
# поэтому сервер и браузер играют по одним и тем же правилам.

from engine.siege import RULES as SIEGE_RULES   # числовые правила — там же,
                                                  # где и у браузерного стека

_siege_cd: "dict[int, float]" = {}     # char_id -> unix-секунда удара


def siege_cooldown_left(char_id: int, now=None) -> int:
    from engine import siege as S
    now = time.time() if now is None else now
    return max(0, int(S.RULES["cooldown"] - (now - _siege_cd.get(int(char_id), 0))))


async def siege_state(session, character) -> dict:
    """Что видит герой на клетке осады: роль, прочность, срок, кулдаун."""
    from engine import siege as S

    await sweep(session)
    sieges = await active_sieges(session, character.location_id)
    if not sieges:
        return {"ok": False, "reason": "Здесь нет осады."}
    ev = sieges[0]
    attacker = S.attacker_of({"attacker": ev.key})
    from core import factions as core_factions
    role = S.role_for(core_factions.allegiance(character), attacker)
    loc = await session.get(Location, ev.location_id) if ev.location_id else None
    left = 0
    if ev.until is not None:
        left = max(0, int((_aware(ev.until) - _now()).total_seconds() // 60))
    return {"ok": True, "event_id": ev.id, "attacker": attacker,
            "role": role, "hp": int(ev.hp or 0), "max_hp": int(ev.max_hp or 0),
            "left_min": left, "castle": (loc.name if loc else "—"),
            "cooldown": siege_cooldown_left(character.id)}


async def siege_hit(session, character) -> dict:
    """Один удар: штурм или починка. Правила и числа — из engine/siege."""
    from engine import siege as S
    from engine.currency import add_currency
    from core import factions as core_factions

    st = await siege_state(session, character)
    if not st["ok"]:
        return st
    if st["cooldown"] > 0:
        return {"ok": False, "reason": f"Ты только что бил. Отдышись {st['cooldown']} с."}
    ev = await session.get(WorldEvent, st["event_id"])
    if ev is None or not ev.is_active:
        return {"ok": False, "reason": "Осада уже снята."}

    roll = S.strike_roll(st["role"], character.level)
    hp, outcome = S.apply_roll(ev.hp, ev.max_hp, st["role"], roll)
    ev.hp = hp
    captured = outcome == "captured"
    if captured:
        ev.is_active = False
    _siege_cd[int(character.id)] = time.time()

    gold = S.gold_for(st["role"], captured)
    if gold:
        add_currency(character, bronze=gold)
    side = (st["attacker"] if st["role"] == "assault"
            else S.defender_faction(st["castle"]))
    bump = S.RULES["rep_hit"] + (S.RULES["rep_capture"] if captured else 0)
    rep = core_factions.load(character)
    S.bump_side(rep, side, bump, core_factions.MIN_REP, core_factions.MAX_REP)
    core_factions.save(character, rep)

    if captured:
        from core.legends import record_server_first
        await record_server_first(
            session, f"siege-capture:{ev.location_id}",
            f"Первое падение цитадели: {st['castle']}", character)

    await session.flush()
    return {"ok": True, "role": st["role"], "roll": roll, "outcome": outcome,
            "hp": hp, "max_hp": int(ev.max_hp or 0), "gold": gold,
            "rep": bump, "side": side, "castle": st["castle"]}


async def siege_begin(session, castle_location_id: int, attacking_faction: str,
                      hours=None) -> WorldEvent:
    """Заварушка: админская кнопка и автотесты идут только через неё,
    чтобы дефолты hp/hours жили в одном месте — RULES движка."""
    from engine import siege as S
    from core import factions as core_factions
    if attacking_faction not in core_factions.FACTIONS:
        raise ValueError("Неизвестная фракция")
    loc = await session.get(Location, int(castle_location_id))
    if loc is None:
        raise ValueError("Замок не найден")
    if await active_sieges(session, loc.id):
        raise ValueError("Этот замок уже осаждают")
    return await start_siege(session, loc.id, attacking_faction,
                             hp=S.RULES["hp"],
                             hours=S.RULES["hours"] if hours is None else float(hours))
