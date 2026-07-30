"""Мировые боссы: цель для всего сервера.

Пожиратель Глубин формально был боссом, но это обычный моб с большими
числами, стоящий на клетке: первый добежавший забирал всё.

Мировой босс — событие, а не клетка. Он появляется по воле админа или сам,
живёт ограниченное время и держит общий счётчик урона: вклад вносят все
игроки, награда идёт по вкладу. Механика таймеров, вестей и летописи взята
у `engine/cataclysm.py` — незачем изобретать второй раз.

Фазы: на половине здоровья босс призывает свиту — она встаёт в очередь
боя, которая уже есть в `engine/combat.py`.
"""
import random
import time

from engine import audit, data, factions, items, rules
from engine.models import Reply

BOSS = "worldboss"          # активный босс в settings
LOG = "worldboss_log"       # летопись сражений
MAX_LOG = 40

# key -> параметры. hp считается на весь сервер, а не на одного героя.
BOSSES = {
    "leviathan": dict(
        name="Левиафан Бездны", icon="🐙", hp=4000, damage=30, defense=12,
        level=10, hours=6, mob=6,
        omen="Вода в колодцах почернела и отступила.",
        story="Из расщелины поднимается то, чему нет имени. Щупальца"
              " перекрывают небо.",
        loot=(2, 7)),
    "wyrm": dict(
        name="Пепельный Змей", icon="🐉", hp=6000, damage=38, defense=16,
        level=14, hours=8, mob=4,
        omen="С гор сходит пепел — значит, он проснулся.",
        story="Чешуя раскалена добела. Каждый выдох превращает камень в стекло.",
        loot=(2, 5)),
    "warden": dict(
        name="Страж Забытых", icon="💀", hp=3000, damage=26, defense=20,
        level=8, hours=5, mob=2,
        omen="Мёртвые в Катакомбах встали разом и замерли.",
        story="Он охраняет то, что давно следовало сжечь. И не устаёт.",
        loot=(5, 7)),
}

ORDER = ["warden", "leviathan", "wyrm"]
PHASE_AT = 0.5              # доля HP, на которой призывается свита
MIN_SHARE = 0.02            # ниже этого вклада награду не дают


def kind(key):
    return BOSSES.get(key)


def title(key):
    b = BOSSES.get(key) or {}
    return f"{b.get('icon', '❓')} {b.get('name', key)}"


# ── состояние ───────────────────────────────────────────────

def active(store):
    """Живой босс или None. Просроченный уходит сам."""
    ev = store.settings.get(BOSS)
    if not isinstance(ev, dict) or not ev:
        return None
    if time.time() >= float(ev.get("until", 0)):
        _finish(store, ev, won=False)
        return None
    if int(ev.get("hp", 0)) <= 0:
        return None
    return ev


def summon(store, key, loc=None, actor=None, source="panel", hours=None):
    """Призвать босса. Один на мир: пока жив прежний, нового не будет."""
    b = BOSSES.get(key)
    if not b:
        raise ValueError("Неизвестный босс")
    if active(store):
        raise ValueError("Мировой босс уже бродит по землям")
    if loc is None:
        loc = _pick_loc()
    loc = int(loc)
    if not (0 <= loc < len(data.LOCATIONS)):
        raise ValueError("Локация не найдена")

    dur = int(float(hours if hours is not None else b["hours"]) * 3600)
    now = int(time.time())
    ev = {"key": key, "hp": int(b["hp"]), "max_hp": int(b["hp"]),
          "loc": loc, "started": now, "until": now + max(300, dur),
          "damage": {}, "phase": 0}
    store.settings[BOSS] = ev
    where = data.LOCATIONS[loc][0]
    audit.record(store, actor, "Мировой босс", title(key),
                 f"{where}, {b['hp']} HP", source)
    _shout(store,
           f"{title(key)}\n<i>{b['omen']}</i>\n\n{b['story']}\n"
           f"📍 {where} · ❤️ {b['hp']} · ⚔️ уровень {b['level']}+\n"
           f"<i>Бить может каждый — награда по вкладу. Кнопка «🏰 Босс» в меню.</i>")
    store.save()
    return ev


def _pick_loc():
    """Босс приходит в опасные земли, а не в деревню."""
    risky = [i for i, l in enumerate(data.LOCATIONS)
             if l[2] in ("dangerous", "dungeon", "boss")]
    return random.choice(risky) if risky else 0


def dismiss(store, actor=None, source="panel"):
    """Развеять босса досрочно, без наград."""
    ev = store.settings.get(BOSS)
    if not ev:
        return None
    _finish(store, ev, won=False)
    audit.record(store, actor, "Босс развеян", title(ev["key"]), "", source)
    return ev


# ── бой ─────────────────────────────────────────────────────

def hit(store, p, damage):
    """Записать урон игрока. Возвращает (осталось HP, фаза сменилась?)."""
    ev = active(store)
    if ev is None:
        return 0, False
    dealt = max(1, int(damage))
    ev["hp"] = max(0, int(ev["hp"]) - dealt)
    dmg = ev.setdefault("damage", {})
    dmg[str(p.tg_id)] = int(dmg.get(str(p.tg_id), 0)) + dealt

    phased = False
    if not ev.get("phase") and ev["hp"] <= ev["max_hp"] * PHASE_AT:
        ev["phase"] = 1
        phased = True
    if ev["hp"] <= 0:
        _finish(store, ev, won=True)
    else:
        store.save()
    return ev["hp"], phased


def contribution(ev, p):
    """Доля игрока в общем уроне (0..1)."""
    dmg = ev.get("damage") or {}
    total = sum(int(v) for v in dmg.values()) or 1
    return int(dmg.get(str(p.tg_id), 0)) / total


def _finish(store, ev, won):
    """Закрыть событие: раздать награды победителям или просто убрать."""
    store.settings[BOSS] = {}
    key = ev.get("key", "?")
    b = BOSSES.get(key) or {}
    if won:
        _reward_all(store, ev, b)
        _shout(store, f"🏆 <b>{title(key)} повержен!</b>\n"
                      f"<i>Земля выдыхает. Награды разосланы по вкладу.</i>")
    else:
        _shout(store, f"🌫 {title(key)} уходит обратно во тьму. В другой раз.")
    log = store.settings.get(LOG)
    if not isinstance(log, list):
        log = []
    log.append({"ts": int(time.time()), "key": key, "won": bool(won),
                "heroes": len(ev.get("damage") or {}),
                "loc": int(ev.get("loc", 0))})
    store.settings[LOG] = log[-MAX_LOG:]
    store.save()


def _reward_all(store, ev, b):
    """Награда по вкладу: золото, опыт и шанс на трофей у лучших."""
    dmg = ev.get("damage") or {}
    total = sum(int(v) for v in dmg.values()) or 1
    lo, hi = b.get("loot", (0, len(data.ITEMS) - 1))
    best = max(dmg, key=lambda k: int(dmg[k])) if dmg else None

    for tg_id, dealt in dmg.items():
        p = store.players.get(int(tg_id))
        if p is None:
            continue
        share = int(dealt) / total
        if share < MIN_SHARE:
            continue
        gold = max(10, int(b.get("hp", 1000) * share * 0.5))
        exp = max(10, int(b.get("hp", 1000) * share * 0.8))
        p.gold += gold
        levels = rules.add_exp(p, exp)
        lines = [f"🏆 <b>{title(ev['key'])} повержен!</b>",
                 f"Твой вклад: <b>{int(share * 100)}%</b>",
                 f"💰 +{gold} 🪙   ⭐ +{exp}"]
        # Трофей достаётся лучшему бойцу и по удаче — остальным сверху 20%.
        if str(tg_id) == str(best) or share > 0.2:
            idx = random.randint(lo, min(hi, len(data.ITEMS) - 1))
            p.inventory.append(idx)
            inst = items.create(store, idx, source="dungeon", owner=p.tg_id,
                                luck=p.luck, detail=title(ev["key"]))
            it = rules.item(idx)
            name = items.title(inst) if inst else it["name"]
            lines.append(f"🎁 Трофей: {it['icon']} <b>{name}</b>")
        lines.extend(factions.award(store, p, "boss_slain"))
        if levels:
            lines.append(f"🎖 Новый уровень: {p.level}!")
        store.save_player(p)
        _tell(store, p.tg_id, "\n".join(lines))


# ── экраны ──────────────────────────────────────────────────

def card(store, p):
    """Экран босса: где он, сколько осталось, кнопка удара."""
    ev = active(store)
    if ev is None:
        return Reply(text="🏰 <b>Мировой босс</b>\n\n<i>Сейчас в мире тихо. "
                          "Когда придёт беда покрупнее — все узнают.</i>",
                     keyboard=[[("◀️ Меню", "menu")]])
    b = BOSSES[ev["key"]]
    where = data.LOCATIONS[ev["loc"]][0] if ev["loc"] < len(data.LOCATIONS) else "?"
    left = max(0, int(ev["until"] - time.time())) // 60
    share = contribution(ev, p)
    here = p.loc == ev["loc"]

    rows = []
    if here and p.level >= b["level"]:
        rows.append([("⚔️ Ударить", "bosshit")])
    lines = [
        f"{title(ev['key'])}\n<i>{b['story']}</i>\n",
        f"❤️ {ev['hp']}/{ev['max_hp']}",
        rules.bar(ev["hp"], ev["max_hp"], "🟥"),
        f"\n📍 {where} · ⏳ ещё ~{left} мин",
        f"👥 Бьются: {len(ev.get('damage') or {})} · твой вклад {int(share * 100)}%",
    ]
    if ev.get("phase"):
        lines.append("\n🔥 <i>Вторая фаза: босс призвал свиту.</i>")
    if not here:
        lines.append(f"\n⚠️ <i>Ты не в этой локации — доберись до {where}.</i>")
    elif p.level < b["level"]:
        lines.append(f"\n⚠️ <i>Нужен {b['level']} уровень, у тебя {p.level}.</i>")
    rows.append([("🔄 Обновить", "boss"), ("◀️ Меню", "menu")])
    return Reply(text="\n".join(lines), keyboard=rows)


def strike(store, p):
    """Удар по боссу: считаем урон героя и его вклад."""
    ev = active(store)
    if ev is None:
        return Reply(alert="Босса уже нет.")
    b = BOSSES[ev["key"]]
    if p.loc != ev["loc"]:
        return Reply(alert="Босс не здесь — сначала доберись до него.")
    if p.level < b["level"]:
        return Reply(alert=f"Нужен {b['level']} уровень.")
    if p.hp <= 1:
        return Reply(alert="Ты слишком слаб. Отдохни или найди лекаря.")

    dealt, crit = rules.attack_roll(p, b["defense"])
    left, phased = hit(store, p, dealt)

    back = max(0, int(b["damage"] * random.uniform(0.5, 1.0))
               - rules.stats(p, store)["defense"] // 2)
    p.hp = max(1, p.hp - back)
    store.save_player(p)

    if left <= 0:
        return Reply(text=f"🏆 <b>Ты нанёс последний удар!</b>\n\n"
                          f"{title(ev['key'])} рушится наземь.\n"
                          f"<i>Награды разошлись всем, кто бился.</i>",
                     keyboard=[[("◀️ Меню", "menu")]])
    if phased:
        _shout(store, f"🔥 {title(ev['key'])} призывает свиту! Половина позади.")
    r = card(store, p)
    r.alert = (f"{'КРИТ! ' if crit else ''}Ты нанёс {dealt}. "
               f"Получил {back}. Осталось {left}.")
    return r


def history(store, limit=10):
    log = store.settings.get(LOG) or []
    return list(reversed(log))[:limit]


def _shout(store, text):
    from engine import adminops
    adminops.queue_all(store, text)


def _tell(store, tg_id, text):
    from engine import adminops
    adminops.queue(store, int(tg_id), text)
