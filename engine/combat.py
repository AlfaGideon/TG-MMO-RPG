"""Пошаговый бой. Бой с одним врагом, но во время катаклизма к нему
могут подтянуться другие твари — они ждут очереди в `queue`."""
import random

from engine import (cataclysm, craft, data, death, factions, items, party,
                    quests, respawn, rules, texts)
from engine.models import Reply


def start(p, mob_index, ambush=False, store=None):
    """Начать бой. `ambush` — тварь напала сама и бьёт первой."""
    from engine import stash
    if stash.offline_protected(p):
        return Reply(alert="Ты офлайн: нападения отключены.")
    m = data.MOBS[mob_index]
    p.combat = {"mob": mob_index, "mob_hp": m[3], "round": 0, "log": [],
                "defend": False, "queue": [], "ambush": bool(ambush)}
    if ambush:
        # Внезапный удар: за неожиданность игрок платит одним пропущенным.
        dmg, dodged = rules.mob_roll(p, m[4])
        if store is not None:
            dmg = int(dmg * cataclysm.effects(store, p.loc).get("damage", 1.0))
        p.combat["log"].append(f"⚡ <b>{m[0]} нападает из засады!</b>")
        if dodged:
            p.combat["log"].append("💨 Ты успел отпрянуть.")
        else:
            p.hp -= dmg
            p.combat["log"].append(f"👾 Внезапный удар на {dmg}.")
        if p.hp <= 0:
            return _finish_lose(p, store)
    return view(p)


def join(p, mob_index):
    """Подтянуть тварь к идущему бою: встанет в очередь после текущей."""
    if not p.combat:
        return False
    queue = p.combat.setdefault("queue", [])
    if len(queue) >= 3:                  # больше трёх в хвосте не копим
        return False
    queue.append(int(mob_index))
    p.combat.setdefault("log", []).append(
        f"➕ {data.MOBS[mob_index][0]} присоединяется к бою!")
    return True


def reinforce(p, store):
    """Шанс, что на шум боя прибежит соседняя тварь. Только в катаклизм.

    Берём тварь с соседней клетки и уводим её оттуда: подкрепление не
    появляется из воздуха и не поджидает игрока второй раз.
    """
    from engine import world as W

    st = p.combat
    if not st or len(st.get("queue") or []) >= 3:
        return None
    chance = cataclysm.effects(store, p.loc).get("join", 0.0)
    if chance <= 0 or random.random() >= chance:
        return None
    near = []
    for dx, dy in W.DIRS.values():
        c = W.cell_at(store.world, p.loc, p.x + dx, p.y + dy, getattr(p, "floor", 0))
        if c is not None and c.mob >= 0:
            near.append(c)
    if not near:
        return None
    c = random.choice(near)
    mob_index = c.mob
    c.mob = -1
    join(p, mob_index)
    return mob_index


def _next_foe(p):
    """Сменить павшего врага на следующего из очереди. True, если бой идёт."""
    st = p.combat
    queue = st.get("queue") or []
    if not queue:
        return False
    nxt = queue.pop(0)
    st["mob"], st["mob_hp"] = nxt, data.MOBS[nxt][3]
    st["defend"] = False
    st["log"].append(f"👾 На смену выходит {data.MOBS[nxt][0]}!")
    return True


def view(p):
    return Reply(text=texts.battle_view(p, p.combat), keyboard=[
        [("⚔️ Атака", "fight:hit"), ("🛡 Защита", "fight:block")],
        [("✨ Умение", "fight:skill"), ("🏃 Бежать", "fight:flee")],
    ])


def _slay(p, world, store=None):
    """Враг повержен: награда за него, затем следующий из очереди или итог."""
    st = p.combat
    m = data.MOBS[st["mob"]]
    gold, exp, lines = _reward(p, m, world, store)
    if _next_foe(p):
        # Бой не окончен: показываем добычу строкой в логе и идём дальше.
        st["log"].append(f"☠️ {m[0]} повержен · +{gold} 🪙 +{exp} ⭐")
        return view(p)
    p.combat = {}
    return Reply(text="\n".join(lines), keyboard=[
        [("🧭 Продолжить путь", "world")],
        [("🔨 Мастерская", "craft"), ("🧙 Профиль", "profile")],
        [("◀️ Меню", "menu")],
    ])


def _reward(p, m, world, store=None):
    """Начислить награду за поверженную тварь. Возвращает (золото, опыт, строки)."""
    st = p.combat
    # Бедствие щедрее/скупее на награду: множители из engine.cataclysm.
    eff = cataclysm.effects(store, p.loc) if store is not None else {}
    gold = max(1, int(m[6] * eff.get("gold", 1.0)))
    exp = max(1, int(m[7] * eff.get("loot", 1.0)))
    # В отряде доля каждого меньше номинала, но суммарно группа получает больше.
    if store is not None:
        k = party.bonus(store, p)
        gold, exp = max(1, int(gold * k)), max(1, int(exp * k))
    p.gold += gold
    p.kills += 1
    levels = rules.add_exp(p, exp)

    if not (p.combat.get("queue") or []):
        cell = world.get(f"{p.loc}:{p.x}:{p.y}")
        if cell and store is not None:
            respawn.schedule_mob(store, cell)   # вернётся сюда через время
        elif cell:
            cell.mob = -1

    loot = rules.loot_roll(st["mob"])
    lines = [f"🎉 <b>Победа!</b>\n\nТы поверг: {m[0]}",
             f"💰 +{gold} 🪙   ⭐ +{exp} опыта"]
    if store is not None:
        alarm = cataclysm.banner(store, p.loc)
        if alarm:
            lines.append(alarm)
    if loot >= 0:
        p.inventory.append(loot)
        # Именной экземпляр со своим ID и статами — если есть куда записать.
        inst = None
        if store is not None:
            inst = items.create(store, loot, source="mob", owner=p.tg_id,
                                luck=p.luck, detail=m[0])
        if inst is not None:
            lines.append(f"📦 Добыча: {inst['icon']} <b>{items.title(inst)}</b>")
            lines.append(f"   <code>{items.tag(inst)}</code> · {items.stats_line(inst)}")
        else:
            it = rules.item(loot)
            lines.append(f"📦 Добыча: {it['icon']} {it['name']}")
    if store is not None:
        mat = craft.loot_material(store, p.tg_id, st["mob"], p.luck)
        if mat >= 0:
            name, icon, _r, _pr = craft.material(mat)
            lines.append(f"🔩 Ресурс: {icon} {name}")
    if store is not None:                      # соратникам рядом — их доля
        lines.extend(party.share(store, p, m[6], m[7]))
        lines.extend(factions.on_kill(store, p, st["mob"]))
    for q in quests.on_kill(p, st["mob"]):     # охотничьи задания
        lines.append(f"📜 Задание «{quests.fields(q)['name']}» — можно сдавать!")
    if levels:
        lines.append(f"\n🎖 <b>Новый уровень: {p.level}!</b> Здоровье восстановлено.")
    return gold, exp, lines


def _finish_lose(p, store=None):
    """Поражение: золото остаётся надгробием на месте гибели, герой ранен."""
    m = data.MOBS[p.combat["mob"]]
    return death.defeat(store, p, m[0])


def action(p, what, world, store=None):
    st = p.combat
    if not st:
        return Reply(alert="Бой уже закончен.")
    m = data.MOBS[st["mob"]]
    st["round"] += 1
    st["log"] = []

    if what == "flee":
        # От своры уйти труднее: каждый в хвосте очереди режет шанс.
        chance = 0.6 - 0.15 * len(st.get("queue") or [])
        if random.random() < max(0.15, chance):
            p.combat = {}
            return Reply(text="🏃 Ты сбежал с поля боя. Жизнь дороже чести.",
                         keyboard=[[("🧭 В мир", "world")], [("◀️ Меню", "menu")]])
        st["log"].append("🏃 Сбежать не вышло!")
    elif what == "skill":
        cost = 15
        if p.mp < cost:
            return Reply(alert="Недостаточно маны!")
        p.mp -= cost
        s = rules.stats(p, store)
        from engine import hero
        power = hero.magic_power(p)          # дар к магии усиливает умение
        dmg = int((s["intelligence"] + s["damage"]) * 1.6 * power)
        st["mob_hp"] -= dmg
        mark = f" {hero.magic_short(getattr(p, 'magic', []))}" if power > 1 else ""
        st["log"].append(f"✨ Умение наносит {dmg} урона!{mark}")
    elif what == "block":
        st["defend"] = True
        st["log"].append("🛡 Ты уходишь в глухую оборону.")
    else:
        dmg, crit = rules.attack_roll(p, m[5])
        st["mob_hp"] -= dmg
        st["log"].append(f"⚔️ {'КРИТ! ' if crit else ''}Ты наносишь {dmg} урона.")

    if st["mob_hp"] <= 0:
        return _slay(p, world, store)

    if store is not None:
        reinforce(p, store)              # в катаклизм на шум сбегаются другие

    mdmg, dodged = rules.mob_roll(p, m[4])
    if store is not None:
        mdmg = int(mdmg * cataclysm.effects(store, p.loc).get("damage", 1.0))
    if st.get("defend"):
        mdmg //= 2
        st["defend"] = False
    p.hp -= mdmg
    st["log"].append("💨 Ты уклонился!" if dodged else f"👾 {m[0]} бьёт на {mdmg}.")

    if p.hp <= 0:
        return _finish_lose(p, store)
    return view(p)
