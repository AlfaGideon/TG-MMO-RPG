"""Пошаговый бой."""
from engine import data, rules, texts
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


def _finish_win(p, world):
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
        lines.append(f"📦 Добыча: {rules.item(loot)['icon']} {rules.item(loot)['name']}")
    if levels:
        lines.append(f"\n🎖 <b>Новый уровень: {p.level}!</b> Здоровье восстановлено.")
    p.combat = {}
    return Reply(text="\n".join(lines), keyboard=[
        [("🧭 Продолжить путь", "world")],
        [("🧙 Профиль", "profile"), ("◀️ Меню", "menu")],
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


def action(p, what, world):
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
        s = rules.stats(p)
        dmg = int((s["intelligence"] + s["damage"]) * 1.6)
        st["mob_hp"] -= dmg
        st["log"].append(f"✨ Умение наносит {dmg} урона!")
    elif what == "block":
        st["defend"] = True
        st["log"].append("🛡 Ты уходишь в глухую оборону.")
    else:
        dmg, crit = rules.attack_roll(p, m[5])
        st["mob_hp"] -= dmg
        st["log"].append(f"⚔️ {'КРИТ! ' if crit else ''}Ты наносишь {dmg} урона.")

    if st["mob_hp"] <= 0:
        return _finish_win(p, world)

    mdmg, dodged = rules.mob_roll(p, m[4])
    if st.get("defend"):
        mdmg //= 2
        st["defend"] = False
    p.hp -= mdmg
    st["log"].append("💨 Ты уклонился!" if dodged else f"👾 {m[0]} бьёт на {mdmg}.")

    if p.hp <= 0:
        return _finish_lose(p)
    return view(p)
