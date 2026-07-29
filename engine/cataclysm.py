"""Катаклизмы: живые бедствия мира — рельеф, твари и награды меняются.

Бедствие живёт ограниченное время, перекраивает клетки локации (или всего
мира) и откатывается обратно, когда стихает: перед правкой снимается слепок
затронутых клеток, поэтому ручная работа админа не теряется.

Случайность берётся из отдельного сида `seeds['cataclysm']` — один и тот же
набор сидов даёт ту же череду бед, мир воспроизводим.
"""
import random
import time

from engine import audit, data
from engine import world as W
from engine.cataclysm_kinds import KINDS, MOB_MULT, ORDER  # noqa: F401

GLOBAL = -1                 # loc == -1 — накрыло весь мир
EVENTS = "cataclysms"       # активные события в settings
LOG = "cataclysm_log"       # летопись бедствий
HORDE = "cataclysm_horde"   # клетки, куда подселены твари сверх мирной нормы
COUNTER = "cataclysm_n"     # счётчик для воспроизводимой случайности
MAX_LOG = 60


def kind(key):
    return KINDS.get(key)


def title(key):
    k = KINDS.get(key) or {}
    return f"{k.get('icon', '❓')} {k.get('name', key)}"


# ── хранилище событий ───────────────────────────────────────

def _events(store):
    lst = store.settings.get(EVENTS)
    if not isinstance(lst, list):
        lst = []
        store.settings[EVENTS] = lst
    return lst


def _rng(store):
    """Случайность бедствий: свой сид + счётчик, чтобы не повторяться."""
    seeds = W.seeds_of(store.settings)
    n = int(store.settings.get(COUNTER, 0)) + 1
    store.settings[COUNTER] = n
    return random.Random(seeds["cataclysm"] * 1_000_003 + n * 7919)


def active(store, loc=None):
    """Живые сейчас бедствия (истёкшие снимаются автоматически)."""
    tick(store)
    out = _events(store)
    if loc is None:
        return list(out)
    loc = int(loc)
    return [e for e in out if int(e["loc"]) in (loc, GLOBAL)]


def effects(store, loc):
    """Множители правил для локации: мобы, урон, добыча, золото, отдых.

    `ambush`/`join` не перемножаются, а берутся по максимуму: два бедствия
    не должны давать шанс больше единицы. Остальное — произведение.
    """
    eff = {"mob_rate": 1.0, "damage": 1.0, "loot": 1.0, "gold": 1.0, "rest": 1.0}
    worst = {"ambush": 0.0, "join": 0.0}
    for e in active(store, loc):
        k = KINDS.get(e["kind"]) or {}
        for key in eff:
            eff[key] *= float(k.get(key, 1.0))
        for key in worst:
            worst[key] = max(worst[key], float(k.get(key, 0.0)))
    eff.update(worst)
    return eff


def raging(store, loc):
    """Бушует ли что-то здесь. Дешевле, чем считать множители."""
    return bool(active(store, loc))


def banner(store, loc):
    """Строка-предупреждение для игрока в клетке (или пустая строка)."""
    live = active(store, loc)
    if not live:
        return ""
    parts = []
    for e in live:
        left = max(0, int(e["until"] - time.time())) // 60
        where = "весь мир" if int(e["loc"]) == GLOBAL else "здесь"
        parts.append(f"{title(e['kind'])} · {where} · ещё {left} мин")
    return "⚠️ " + " | ".join(parts)


# ── орда и агрессия (реализация в engine/horde.py) ──────────

def rebalance(store, rng=None):
    """Свести число тварей к норме: ×MOB_MULT в беде, обычное в покое."""
    from engine import horde
    return horde.rebalance(store, rng)


def prowl(store, p, rng=None):
    """Тварь с соседней клетки бросается на игрока сама (только в беду)."""
    from engine import horde
    return horde.prowl(store, p, rng)


# ── удар и откат ────────────────────────────────────────────

def strike(store, kind_key, loc=GLOBAL, actor=None, source="panel", hours=None):
    """Обрушить бедствие. Возвращает событие. Клетки правятся со слепком."""
    k = KINDS.get(kind_key)
    if not k:
        raise ValueError("Неизвестный катаклизм")
    loc = int(loc)
    if loc != GLOBAL and not (0 <= loc < len(data.LOCATIONS)):
        raise ValueError("Локация не найдена")
    for e in active(store, None):
        if e["kind"] == kind_key and int(e["loc"]) == loc:
            raise ValueError(f"{title(kind_key)} уже бушует здесь")
    rng = _rng(store)
    now = int(time.time())
    dur = int(float(hours if hours is not None else k["hours"]) * 3600)
    ev = {"id": now * 1000 + rng.randrange(999), "kind": kind_key, "loc": loc,
          "started": now, "until": now + max(60, dur), "snapshot": {}, "cells": 0}
    _apply(store, ev, k, rng)
    _events(store).append(ev)
    born, _ = rebalance(store, rng)      # тварей становится вдвое больше
    ev["horde"] = born
    _remember(store, ev, "начался")
    where = "по всему миру" if loc == GLOBAL else f"в локации «{data.LOCATIONS[loc][0]}»"
    audit.record(store, actor, "Катаклизм", title(kind_key),
                 f"{where}, клеток: {ev['cells']}", source)
    _shout(store, f"{title(kind_key)}\n<i>{k['omen']}</i>\n\n{k['story']}\n"
                  f"📍 {where.capitalize()} · продлится ~{dur // 3600} ч.\n"
                  f"👾 Тварей вдвое больше (+{born}), и они нападают сами!")
    store.save()
    return ev


def _apply(store, ev, k, rng):
    """Перекроить клетки: слепок → правки. Дороги-швы не трогаем.

    Тварей здесь не расставляем: за их число целиком отвечает rebalance,
    иначе удвоение считалось бы от уже раздутой базы.
    """
    loc = int(ev["loc"])
    busy = {f"{p.loc}:{p.x}:{p.y}" for p in store.players.values()}
    pool = [c for c in store.world.values()
            if (loc == GLOBAL or c.loc == loc) and not c.link
            and c.key not in busy and (c.x, c.y) != W.SPAWN]
    rng.shuffle(pool)
    take = max(1, int(len(pool) * float(k.get("spread", 0.3))))
    snap = {}
    for c in pool[:take]:
        snap[c.key] = [c.tile, c.passable, c.mob, c.chest]
        tile = (k.get("tiles") or {}).get(c.tile)
        if tile:
            c.tile = tile
        if c.passable and c.tile != "road" and rng.random() < k.get("block", 0):
            c.passable, c.tile = False, "wall"
        if c.passable and not c.chest and rng.random() < k.get("chests", 0):
            c.chest = True
    ev["snapshot"] = snap
    ev["cells"] = len(snap)


def end(store, event_id, revert=True, actor=None, source="panel"):
    """Погасить бедствие досрочно и вернуть клетки как было."""
    lst = _events(store)
    ev = next((e for e in lst if int(e["id"]) == int(event_id)), None)
    if not ev:
        return None
    if revert:
        _restore(store, ev)
    lst.remove(ev)
    gone = rebalance(store)[1]           # орда расходится
    _remember(store, ev, "утих")
    audit.record(store, actor, "Катаклизм утих", title(ev["kind"]),
                 f"клеток восстановлено: {ev.get('cells', 0)}", source)
    _shout(store, f"🕊 {title(ev['kind'])} закончился. Земля приходит в себя."
                  + (f"\n👾 Тварей снова обычное число (−{gone})." if gone else ""))
    store.save()
    return ev


def _restore(store, ev):
    """Вернуть клетки по слепку.

    Клетки орды пропускаем по мобу: их мирное значение — «пусто», и его
    выставит rebalance, когда сведёт популяцию к норме. Иначе снятие
    бедствия воскрешало бы тварей, которых игрок уже убил.
    """
    horde = set(store.settings.get(HORDE) or [])
    for key, snap in (ev.get("snapshot") or {}).items():
        c = store.world.get(key)
        if not c:
            continue
        c.tile, c.passable = snap[0], bool(snap[1])
        c.chest = bool(snap[3])
        if key not in horde:
            c.mob = int(snap[2])


_ticking = set()            # защита от рекурсии tick → rebalance → active → tick


def tick(store):
    """Снять всё, чему вышел срок. Возвращает число погашенных бедствий."""
    if id(store) in _ticking:
        return 0
    lst = _events(store)
    now = time.time()
    done = [e for e in lst if now >= float(e.get("until", 0))]
    for ev in done:
        _restore(store, ev)
        lst.remove(ev)
        _remember(store, ev, "утих сам")
        _shout(store, f"🕊 {title(ev['kind'])} стихает — мир зализывает раны.")
    if done:
        _ticking.add(id(store))
        try:
            rebalance(store)             # популяция возвращается к норме
        finally:
            _ticking.discard(id(store))
        store.save()
    return len(done)


def auto(store):
    """Шанс сама-собой начавшейся беды. Зовётся из игрового цикла."""
    tick(store)
    if not store.settings.get("cataclysm_auto", True):
        return None
    chance = float(store.settings.get("cataclysm_chance", 0.02) or 0)
    limit = int(store.settings.get("cataclysm_limit", 2) or 2)
    if chance <= 0 or len(_events(store)) >= max(1, limit):
        return None
    rng = _rng(store)
    if rng.random() >= chance:
        return None
    key = rng.choice(ORDER)
    loc = GLOBAL if rng.random() < 0.15 else rng.randrange(len(data.LOCATIONS))
    try:
        return strike(store, key, loc, actor="Судьба", source="bot")
    except ValueError:
        return None


# ── летопись и вестники ─────────────────────────────────────

def _remember(store, ev, what):
    log = store.settings.get(LOG)
    if not isinstance(log, list):
        log = []
    loc = int(ev["loc"])
    log.append({"ts": int(time.time()), "kind": ev["kind"], "loc": loc,
                "what": what, "cells": int(ev.get("cells", 0))})
    store.settings[LOG] = log[-MAX_LOG:]


def history(store, limit=20):
    log = store.settings.get(LOG) or []
    return list(reversed(log))[:limit]


def place(loc):
    loc = int(loc)
    if loc == GLOBAL:
        return "🌍 Весь мир"
    return data.LOCATIONS[loc][0] if loc < len(data.LOCATIONS) else f"#{loc}"


def _shout(store, text):
    """Разослать весть всем игрокам через общую очередь админ-операций."""
    if not store.settings.get("cataclysm_notify", True):
        return
    from engine import adminops
    adminops.queue_all(store, text)


def card(store, loc):
    """Экран «что происходит» для игрока: чем именно бушует его земля."""
    from engine.models import Reply

    live = active(store, loc)
    if not live:
        return Reply(alert="Сейчас всё спокойно.")
    lines = []
    for e in live:
        k = KINDS.get(e["kind"]) or {}
        left = max(0, int(e["until"] - time.time())) // 60
        lines.append(
            f"{title(e['kind'])}\n<i>{k.get('story', '')}</i>\n"
            f"📍 {place(e['loc'])} · ⏳ ещё ~{left} мин\n"
            f"👾 твари ×{k.get('mob_rate', 1):.2f} · 💥 урон ×{k.get('damage', 1):.2f} · "
            f"📦 добыча ×{k.get('loot', 1):.2f} · 🏕 отдых ×{k.get('rest', 1):.2f}")
    return Reply(text="🌋 <b>Бедствие</b>\n\n" + "\n\n".join(lines),
                 keyboard=[[("◀️ В мир", "world")]])
