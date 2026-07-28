"""Пошаговый бой."""
from engine import craft, data, items, rules, texts
from engine.models import Reply


def start(p, mob_index):
    m = data.MOBS[mob_index]
    p.combat = {"mob": mob_index, "mob_hp": m[3], "round": 0, "log": [], "defend": False}
    return view(p)


def view(p):
    return Reply(text=texts.battle_view(p, p.combat), keyboard=[
        [("⚔️ Атака", "fight:hit"), ("🛡 Защита", "fight:block")],
        [("✨ Умение", "fight:skill"), ("🏃 Бежать", "fight:flee")],
    ])


def _finish_win(p, world, store=None):
    st = p.combat
    m = data.MOBS[st["mob"]]
    gold, exp = m[6], m[7]
    p.gold += gold
    p.kills += 1
    levels = rules.add_exp(p, exp)

    cell = world.get(f"{p.loc}:{p.x}:{p.y}")
    if cell:
        cell.mob = -1

    loot = rules.loot_roll(st["mob"])
    lines = [f"🎉 <b>Победа!</b>\n\nТы поверг: {m[0]}",
             f"💰 +{gold} 🪙   ⭐ +{exp} опыта"]
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
    if levels:
        lines.append(f"\n🎖 <b>Новый уровень: {p.level}!</b> Здоровье восстановлено.")
    p.combat = {}
    return Reply(text="\n".join(lines), keyboard=[
        [("🧭 Продолжить путь", "world")],
        [("🔨 Мастерская", "craft"), ("🧙 Профиль", "profile")],
        [("◀️ Меню", "menu")],
    ])


def _finish_lose(p):
    m = data.MOBS[p.combat["mob"]]
    lost = p.gold // 5
    p.gold -= lost
    p.hp = max(1, rules.stats(p)["max_hp"] // 4)
    p.loc, p.x, p.y = 0, 5, 5
    p.combat = {}
    return Reply(text=(
        f"💀 <b>Поражение...</b>\n\n{m[0]} оказался сильнее. "
        f"Ты очнулся в Погосте Костров.\n\n"
        f"Потеряно: {lost} 🪙"
    ), keyboard=[[("🧭 В мир", "world")], [("◀️ Меню", "menu")]])


def action(p, what, world, store=None):
    st = p.combat
    if not st:
        return Reply(alert="Бой уже закончен.")
    m = data.MOBS[st["mob"]]
    st["round"] += 1
    st["log"] = []

    if what == "flee":
        import random
        if random.random() < 0.6:
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
        return _finish_win(p, world, store)

    mdmg, dodged = rules.mob_roll(p, m[4])
    if st.get("defend"):
        mdmg //= 2
        st["defend"] = False
    p.hp -= mdmg
    st["log"].append("💨 Ты уклонился!" if dodged else f"👾 {m[0]} бьёт на {mdmg}.")

    if p.hp <= 0:
        return _finish_lose(p)
    return view(p)
