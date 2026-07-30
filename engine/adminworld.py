"""Админ-операции над миром: катаклизмы и мировые боссы.

Вынесено из engine/adminops.py, чтобы тот не разрастался. Проверка прав
и запись в журнал — те же самые, через общие require()/Denied.
"""
from engine.adminops import Denied, require

# ── катаклизмы ──────────────────────────────────────────────

def cataclysm_strike(store, actor, kind_key, loc=-1, hours=None, source="panel"):
    """Обрушить бедствие на локацию (loc=-1 — на весь мир)."""
    require(actor, "cataclysms")
    from engine import cataclysm
    try:
        ev = cataclysm.strike(store, kind_key, loc, actor=actor,
                              source=source, hours=hours)
    except ValueError as e:
        raise Denied(str(e))
    return ev, f"{cataclysm.title(kind_key)} → {cataclysm.place(loc)}"


def cataclysm_end(store, actor, event_id, source="panel"):
    require(actor, "cataclysms")
    from engine import cataclysm
    ev = cataclysm.end(store, event_id, revert=True, actor=actor, source=source)
    if ev is None:
        raise Denied("Бедствие уже утихло")
    return ev, cataclysm.title(ev["kind"])


def cataclysm_calm(store, actor, source="panel"):
    """Погасить все бедствия разом и вернуть клетки как было."""
    require(actor, "cataclysms")
    from engine import cataclysm
    live = cataclysm.active(store, None)
    for ev in list(live):
        cataclysm.end(store, ev["id"], revert=True, actor=actor, source=source)
    return len(live)


# ── мировые боссы ───────────────────────────────────────────

def boss_summon(store, actor, key, loc=None, hours=None, source="panel"):
    require(actor, "cataclysms")
    from engine import worldboss
    try:
        ev = worldboss.summon(store, key, loc, actor=actor, source=source,
                              hours=hours)
    except ValueError as e:
        raise Denied(str(e))
    return ev, worldboss.title(key)


def boss_dismiss(store, actor, source="panel"):
    require(actor, "cataclysms")
    from engine import worldboss
    ev = worldboss.dismiss(store, actor, source)
    if ev is None:
        raise Denied("Босса и так нет")
    return ev, worldboss.title(ev["key"])
