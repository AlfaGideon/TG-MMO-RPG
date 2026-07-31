"""Взаимодействие с клеткой: осмотр, разговор, сундук, привал, лечение.

Отдельно от роутера `engine/game.py`, чтобы тот оставался тонким. Функции
чистые: получают игрока и хранилище, возвращают Reply.
"""
import random

from engine import (cataclysm, data, death, factions, items, landmarks, money,
                    respawn, rules)
from engine.models import Reply

BACK_WORLD = [[("◀️ В мир", "world")]]


def look(p, cell, store=None):
    """Осмотр клетки: что тут есть и что с этим делать."""
    from engine import mapview

    found, rows = [], []
    mark = landmarks.of(cell, store)
    if mark is not None:
        found.append(landmarks.note(p, cell, store))
        if not landmarks.visited(p, cell):
            rows.append([(f"{mark['icon']} Изучить", "study")])
    if store is not None:
        from engine import dungeon
        tpl = dungeon.portal_at(store, cell.key)
        if tpl is not None:
            found.append(f"🌀 Портал: <b>{tpl['name']}</b> "
                         f"(ур. {tpl.get('min_level', 1)}+)")
            rows.append([("🕳 Войти в портал", "denter")])
    grave = death.at(store, cell.loc, cell.x, cell.y) if store is not None else None
    if grave is not None:
        whose = "твоя" if int(grave.get("owner", 0)) == int(p.tg_id) else f"{grave.get('name', '?')}"
        found.append(f"🪦 Надгробие ({whose}) — {money.fmt(grave.get('gold', 0))}")
        rows.append([("💰 Забрать", "claim")])
    for q in mapview.others_here(store, p, cell.loc, cell.x, cell.y):
        found.append(f"🔵 Герой: {q.name} (ур. {q.level})")
    if cell.mob >= 0:
        from engine import behavior
        found.append(f"👾 Враг: {data.MOBS[cell.mob][0]} (ур. {data.MOBS[cell.mob][2]})"
                     f" · {behavior.label(cell.mob)}")
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


def talk(npc_index, p=None):
    """Диалог с жителем: торговля, лечение и его задания."""
    from engine import quests

    n = data.NPCS[int(npc_index)]
    if p is not None and factions.refuses(p, npc_index):
        return Reply(text=f"💬 <b>{n[0]}</b>\n\n<i>«Уходи. С такими, как ты, "
                          f"дела не имею.»</i>\n\n"
                          f"{factions.greeting(p, npc_index)}",
                     keyboard=[[("◀️ Назад", "world")]])
    rows = []
    if n[2] == "merchant":
        rows.append([("🛒 Торговать", "shop")])
    if n[2] == "healer":
        rows.append([("💊 Исцелиться", "heal")])
    if n[2] == "smith":
        rows.append([("🔨 Мастерская", "craft")])
    if p is not None:
        rows.extend(quests.offer_rows(p, npc_index))
    rows.append([("◀️ Назад", "world")])
    mood = factions.greeting(p, npc_index) if p is not None else ""
    return Reply(text=f"💬 <b>{n[0]}</b>\n\n<i>{n[1]}</i>{mood}", keyboard=rows)


def heal(p):
    """Лекарь: восстанавливает силы и заодно залечивает раны после смерти."""
    was_wounded = death.wounded(p)
    death.heal_wounds(p)
    s = rules.stats(p)
    p.hp, p.mp = s["max_hp"], s["max_mp"]
    extra = ("\n🩸 Раны затянулись — штраф к статам снят." if was_wounded else "")
    return Reply(text="💊 Лекарь Мира кладёт ладонь тебе на лоб.\n\n"
                      f"❤️ Здоровье и мана полностью восстановлены.{extra}",
                 keyboard=BACK_WORLD)


def chest(p, cell, store):
    """Сундук: золото и, если повезёт, именной предмет.

    Во время бедствия добыча меняется — множители берутся из engine.cataclysm.
    """
    if not cell.chest:
        return Reply(alert="Сундук уже пуст.")
    respawn.schedule_chest(store, cell)     # новый появится в этой локации
    eff = cataclysm.effects(store, p.loc)
    gold = max(1, int(random.randint(10, 45) * eff["gold"]))
    money.earn(p, gold)
    lines = [f"📦 <b>Сундук открыт!</b>\n\nВнутри: {money.fmt(gold)}"]
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
    lines.extend(factions.award(store, p, "chest_opened"))
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
