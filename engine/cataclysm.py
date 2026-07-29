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

GLOBAL = -1                 # loc == -1 — накрыло весь мир
EVENTS = "cataclysms"       # активные события в settings
LOG = "cataclysm_log"       # летопись бедствий
COUNTER = "cataclysm_n"     # счётчик для воспроизводимой случайности
MAX_LOG = 60

# kind -> параметры. tiles — во что превращается тайл, spread — доля клеток,
# block — шанс завала, spawn — шанс подселить тварь, chests — шанс находки.
# mob_rate/damage/loot/gold/rest — множители правил, пока беда идёт.
KINDS = {
    "quake": dict(
        name="Землетрясение", icon="🌋", hours=3, spread=0.40,
        tiles={"grass": "cave", "road": "cave", "village": "cave"},
        block=0.14, spawn=0.03, chests=0.04,
        mob_rate=1.15, damage=1.10, loot=1.05, gold=1.00, rest=0.80,
        omen="Гул из-под земли слышен даже в Погосте Костров.",
        story="Земля вспарывается трещинами, тропы обрушиваются в пустоту."),
    "flood": dict(
        name="Великий потоп", icon="🌊", hours=4, spread=0.45,
        tiles={"grass": "water", "road": "water", "village": "water"},
        block=0.10, spawn=0.02, chests=0.06,
        mob_rate=0.90, damage=1.05, loot=1.10, gold=1.05, rest=0.70,
        omen="Реки вышли из берегов и идут на низины.",
        story="Мутная вода накрыла дороги; уцелевшие тропы стали островами."),
    "wildfire": dict(
        name="Пожар", icon="🔥", hours=2, spread=0.50,
        tiles={"forest": "grass", "village": "grass", "grass": "road"},
        block=0.08, spawn=0.05, chests=0.03,
        mob_rate=1.20, damage=1.20, loot=1.00, gold=1.10, rest=0.60,
        omen="Небо на горизонте стало рыжим от зарева.",
        story="Огонь съедает чащу, оставляя пепел и раскалённые камни."),
    "blizzard": dict(
        name="Ледяная буря", icon="❄️", hours=5, spread=0.55,
        tiles={"water": "wall", "grass": "wall", "road": "road"},
        block=0.06, spawn=0.02, chests=0.02,
        mob_rate=0.85, damage=1.15, loot=1.00, gold=0.95, rest=0.50,
        omen="Ветер принёс мороз, которого не помнят старики.",
        story="Снег заносит тропы, вода схватывается коркой чёрного льда."),
    "bloodmoon": dict(
        name="Кровавая луна", icon="🌕", hours=2, spread=0.60,
        tiles={}, block=0.0, spawn=0.22, chests=0.05,
        mob_rate=1.60, damage=1.25, loot=1.35, gold=1.30, rest=0.75,
        omen="Луна налилась красным — твари осмелели.",
        story="Нежить лезет отовсюду, зато и добыча стала щедрее."),
    "meteor": dict(
        name="Звездопад", icon="☄️", hours=3, spread=0.30,
        tiles={"grass": "cave", "forest": "cave"},
        block=0.12, spawn=0.06, chests=0.18,
        mob_rate=1.10, damage=1.05, loot=1.25, gold=1.20, rest=0.85,
        omen="С неба падают камни, оставляя дымящиеся воронки.",
        story="В кратерах поблёскивает звёздное железо — и что-то шевелится."),
    "plague": dict(
        name="Мор", icon="☠️", hours=6, spread=0.50,
        tiles={"village": "grass"}, block=0.02, spawn=0.10, chests=0.02,
        mob_rate=1.25, damage=1.10, loot=0.90, gold=0.80, rest=0.40,
        omen="По деревням идёт болезнь: костры горят даже днём.",
        story="Живые прячутся, мёртвые ходят. Отдых почти не помогает."),
    "voidrift": dict(
        name="Разлом Пустоты", icon="🌀", hours=2, spread=0.25,
        tiles={"grass": "cave", "road": "cave", "wall": "cave"},
        block=0.05, spawn=0.18, chests=0.10,
        mob_rate=1.45, damage=1.35, loot=1.50, gold=1.40, rest=0.65,
        omen="Ткань мира треснула — из прорехи тянет холодом.",
        story="Пространство свернулось: за каждым поворотом ждёт чужое."),
}

ORDER = ["quake", "flood", "wildfire", "blizzard", "bloodmoon", "meteor",
         "plague", "voidrift"]


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
    """Множители правил для локации: мобы, урон, добыча, золото, отдых."""
    eff = {"mob_rate": 1.0, "damage": 1.0, "loot": 1.0, "gold": 1.0, "rest": 1.0}
    for e in active(store, loc):
        k = KINDS.get(e["kind"]) or {}
        for key in eff:
            eff[key] *= float(k.get(key, 1.0))
    return eff


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
    _remember(store, ev, "начался")
    where = "по всему миру" if loc == GLOBAL else f"в локации «{data.LOCATIONS[loc][0]}»"
    audit.record(store, actor, "Катаклизм", title(kind_key),
                 f"{where}, клеток: {ev['cells']}", source)
    _shout(store, f"{title(kind_key)}\n<i>{k['omen']}</i>\n\n{k['story']}\n"
                  f"📍 {where.capitalize()} · продлится ~{dur // 3600} ч.")
    store.save()
    return ev


def _apply(store, ev, k, rng):
    """Перекроить клетки: слепок → правки. Дороги-швы не трогаем."""
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
        if c.passable and c.mob < 0 and rng.random() < k.get("spawn", 0):
            c.mob = rng.randrange(len(data.MOBS))
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
    _remember(store, ev, "утих")
    audit.record(store, actor, "Катаклизм утих", title(ev["kind"]),
                 f"клеток восстановлено: {ev.get('cells', 0)}", source)
    _shout(store, f"🕊 {title(ev['kind'])} закончился. Земля приходит в себя.")
    store.save()
    return ev


def _restore(store, ev):
    for key, snap in (ev.get("snapshot") or {}).items():
        c = store.world.get(key)
        if not c:
            continue
        c.tile, c.passable = snap[0], bool(snap[1])
        c.mob, c.chest = int(snap[2]), bool(snap[3])


def tick(store):
    """Снять всё, чему вышел срок. Возвращает число погашенных бедствий."""
    lst = _events(store)
    now = time.time()
    done = [e for e in lst if now >= float(e.get("until", 0))]
    for ev in done:
        _restore(store, ev)
        lst.remove(ev)
        _remember(store, ev, "утих сам")
        _shout(store, f"🕊 {title(ev['kind'])} стихает — мир зализывает раны.")
    if done:
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
