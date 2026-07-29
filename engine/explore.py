"""Взаимодействие с клеткой: осмотр, разговор, сундук, привал, лечение.

Отдельно от роутера `engine/game.py`, чтобы тот оставался тонким. Функции
чистые: получают игрока и хранилище, возвращают Reply.
"""
import random

from engine import cataclysm, data, items, rules
from engine.models import Reply

BACK_WORLD = [[("◀️ В мир", "world")]]


def look(p, cell):
    """Осмотр клетки: что тут есть и что с этим делать."""
    found, rows = [], []
    if cell.mob >= 0:
        found.append(f"👾 Враг: {data.MOBS[cell.mob][0]} (ур. {data.MOBS[cell.mob][2]})")
        rows.append([("⚔️ Атаковать", f"hunt:{cell.mob}")])
    if cell.npc >= 0:
        n = data.NPCS[cell.npc]
        found.append(f"💬 {n[0]}")
        rows.append([("💬 Поговорить", f"talk:{cell.npc}")])
    if cell.chest:
        found.append("📦 Сундук!")
        rows.append([("📦 Открыть", "chest")])
    body = "\n".join(found) if found else f"<i>{random.choice(data.EMPTY_LOOK)}</i>"
    rows.append([("◀️ Назад", "world")])
    return Reply(text=f"🔍 <b>Осмотр [{cell.x},{cell.y}]</b>\n<i>{cell.name}</i>\n\n"
                      f"{cell.desc}\n\n{body}", keyboard=rows)


def talk(npc_index):
    n = data.NPCS[int(npc_index)]
    rows = []
    if n[2] == "merchant":
        rows.append([("🛒 Торговать", "shop")])
    if n[2] == "healer":
        rows.append([("💊 Исцелиться", "heal")])
    rows.append([("◀️ Назад", "world")])
    return Reply(text=f"💬 <b>{n[0]}</b>\n\n<i>{n[1]}</i>", keyboard=rows)


def heal(p):
    s = rules.stats(p)
    p.hp, p.mp = s["max_hp"], s["max_mp"]
    return Reply(text="💊 Лекарь Мира кладёт ладонь тебе на лоб.\n\n"
                      "❤️ Здоровье и мана полностью восстановлены.",
                 keyboard=BACK_WORLD)


def chest(p, cell, store):
    """Сундук: золото и, если повезёт, именной предмет.

    Во время бедствия добыча меняется — множители берутся из engine.cataclysm.
    """
    if not cell.chest:
        return Reply(alert="Сундук уже пуст.")
    cell.chest = False
    eff = cataclysm.effects(store, p.loc)
    gold = max(1, int(random.randint(10, 45) * eff["gold"]))
    p.gold += gold
    lines = [f"📦 <b>Сундук открыт!</b>\n\nВнутри: {gold} 🪙"]
    if random.random() < min(0.95, 0.5 * eff["loot"]):
        idx = random.randrange(len(data.ITEMS))
        p.inventory.append(idx)
        inst = items.create(store, idx, source="chest", owner=p.tg_id,
                            luck=p.luck, detail="сундук")
        if inst is not None:
            lines.append(f"И ещё: {inst['icon']} <b>{items.title(inst)}</b>")
            lines.append(f"   <code>{items.tag(inst)}</code> · {items.stats_line(inst)}")
        else:
            it = rules.item(idx)
            lines.append(f"И ещё: {it['icon']} {it['name']}")
    return Reply(text="\n".join(lines), keyboard=BACK_WORLD)


def rest(p, store):
    """Привал. В бедствие отдыхается хуже — множитель `rest`."""
    s = rules.stats(p)
    calm = cataclysm.effects(store, p.loc)["rest"]
    hp = max(1, int(s["max_hp"] // 3 * calm))
    mp = max(1, int(s["max_mp"] // 3 * calm))
    p.hp = min(s["max_hp"], p.hp + hp)
    p.mp = min(s["max_mp"], p.mp + mp)
    note = "\n<i>Бедствие не даёт толком выспаться.</i>" if calm < 1 else ""
    return Reply(text=(f"🏕 <b>Привал</b>\n\nТы отдохнул у костра.\n"
                       f"❤️ +{hp} HP · 💙 +{mp} MP{note}\n\n"
                       f"Сейчас: {p.hp}/{s['max_hp']} HP"),
                 keyboard=BACK_WORLD)
