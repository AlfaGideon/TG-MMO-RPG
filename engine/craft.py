"""Крафт и заточка: рецепты, материалы, кузница.

Материалы падают с мобов и лежат в сумке стопками. По рецепту из них
куётся именной экземпляр (`engine.items`), поэтому у скрафченной вещи
свой ID со значком 🔨 и своя летопись.

Заточка повышает статы экземпляра, но с ростом уровня падает шанс:
неудача не ломает вещь, а лишь съедает плату.
"""
import random

from engine import data, items
from engine.models import Reply

KEY = "materials"           # {tg_id: {material_idx: count}}


# ── материалы ───────────────────────────────────────────────

def _bank(store):
    bank = store.settings.get(KEY)
    if not isinstance(bank, dict):
        bank = {}
        store.settings[KEY] = bank
    return bank


def pouch(store, tg_id):
    """Материалы игрока: {индекс материала: количество}."""
    raw = _bank(store).get(str(tg_id)) or {}
    return {int(k): int(v) for k, v in raw.items() if int(v) > 0}


def add_material(store, tg_id, idx, count=1):
    bank = _bank(store)
    mine = bank.setdefault(str(tg_id), {})
    mine[str(int(idx))] = int(mine.get(str(int(idx)), 0)) + int(count)
    return mine


def take_materials(store, tg_id, need):
    """Списывает материалы, если хватает. True — списано."""
    have = pouch(store, tg_id)
    for idx, count in need.items():
        if have.get(int(idx), 0) < int(count):
            return False
    bank = _bank(store)
    mine = bank.setdefault(str(tg_id), {})
    for idx, count in need.items():
        mine[str(int(idx))] = int(mine.get(str(int(idx)), 0)) - int(count)
    return True


def material(idx):
    """(название, иконка, редкость, цена) по индексу."""
    idx = int(idx)
    if 0 <= idx < len(data.MATERIALS):
        return data.MATERIALS[idx]
    return ("Неизвестный материал", "❔", "common", 1)


def material_line(idx, count):
    name, icon, _rarity, _price = material(idx)
    return f"{icon} {name} ×{count}"


def loot_material(store, tg_id, mob_index, luck=0):
    """Шанс выбить материал с моба. Возвращает индекс или -1."""
    if random.random() > 0.45 + min(0.2, luck / 200):
        return -1
    level = data.MOBS[mob_index][2] if 0 <= mob_index < len(data.MOBS) else 1
    pool = [i for i, m in enumerate(data.MATERIALS) if m[3] <= 4 + level * 7]
    if not pool:
        return -1
    idx = random.choice(pool)
    add_material(store, tg_id, idx, 1)
    return idx


# ── рецепты ─────────────────────────────────────────────────

def recipe(i):
    """(название, иконка, станок, предмет, материалы, цена, мин.уровень)."""
    return data.RECIPES[int(i)]


def recipes_for(station=""):
    """Индексы рецептов станка (пустая строка — все)."""
    return [i for i, r in enumerate(data.RECIPES)
            if not station or r[2] == station]


def can_craft(store, p, i):
    """(можно?, причина). Проверяет уровень, золото и материалы."""
    name, _icon, _st, _idx, need, price, lvl = recipe(i)
    if p.level < lvl:
        return False, f"нужен уровень {lvl}"
    if p.gold < price:
        return False, f"не хватает {price - p.gold} 🪙"
    have = pouch(store, p.tg_id)
    for m, count in need.items():
        if have.get(int(m), 0) < count:
            short = count - have.get(int(m), 0)
            return False, f"не хватает {material(m)[0].lower()} ×{short}"
    return True, ""


def craft(store, p, i):
    """Куёт предмет по рецепту. Возвращает (экземпляр, сообщение)."""
    ok, why = can_craft(store, p, i)
    if not ok:
        return None, why
    name, _icon, _st, idx, need, price, _lvl = recipe(i)
    if not take_materials(store, p.tg_id, need):
        return None, "материалы кончились"
    p.gold -= price
    inst = items.create(store, idx, source="craft", owner=p.tg_id,
                        luck=p.luck, detail=name)
    if inst is None:                       # стопка — кладём в сумку как обычно
        p.inventory.append(int(idx))
        store.save_player(p)
        return None, f"изготовлено: {name}"
    p.inventory.append(int(idx))
    store.save_player(p)
    return inst, f"изготовлено: {items.title(inst)}"


# ── заточка ─────────────────────────────────────────────────

def upgrade_odds(level):
    """(шанс успеха, множитель цены) для перехода на level+1."""
    level = int(level)
    if level >= data.MAX_UPGRADE:
        return 0.0, 0
    return data.UPGRADE_ODDS[level]


def upgrade_price(inst):
    level = int(inst.get("upgrade") or 0)
    _chance, mult = upgrade_odds(level)
    if not mult:
        return 0
    base = items.price(inst)
    return max(5, int(base * 0.25 * mult))


def upgrade(store, p, uid):
    """Заточка экземпляра. Возвращает (успех?, сообщение)."""
    inst = items.get(store, uid)
    if inst is None:
        return False, "предмет не найден"
    if int(inst.get("owner") or 0) != int(p.tg_id):
        return False, "это не твоя вещь"
    level = int(inst.get("upgrade") or 0)
    if level >= data.MAX_UPGRADE:
        return False, f"максимум +{data.MAX_UPGRADE}"
    chance, _mult = upgrade_odds(level)
    cost = upgrade_price(inst)
    if p.gold < cost:
        return False, f"не хватает {cost - p.gold} 🪙"
    p.gold -= cost
    store.save_player(p)
    if random.random() > chance:
        items.record(store, inst, "upgraded", p.tg_id,
                     detail=f"неудача на +{level + 1}", price=cost)
        return False, f"заточка сорвалась · −{cost} 🪙"
    inst["upgrade"] = level + 1
    for k in list(inst.get("stats") or {}):
        inst["stats"][k] = int(round(inst["stats"][k] * 1.1)) or 1
    items.record(store, inst, "upgraded", p.tg_id,
                 detail=f"до +{level + 1}", price=cost)
    return True, f"заточено до +{level + 1}"


# ── экраны бота ─────────────────────────────────────────────

def workshop(store, p):
    """Главный экран мастерской: материалы и станки."""
    mine = pouch(store, p.tg_id)
    lines = ["🔨 <b>Мастерская</b>", f"🪙 <b>{p.gold}</b>", ""]
    if mine:
        lines.append("<b>Материалы:</b>")
        for idx in sorted(mine):
            lines.append("• " + material_line(idx, mine[idx]))
    else:
        lines.append("<i>Материалов нет — бей мобов, они выпадают в бою.</i>")
    lines.append("")
    lines.append("<i>Выбери станок, чтобы посмотреть рецепты.</i>")

    rows = [[(f"{ic} {nm}", f"craft:{key}") for key, (ic, nm) in data.STATIONS.items()]]
    rows.append([("⚡ Заточка", "sharpen:0")])
    rows.append([("🎒", "bag"), ("◀️ Меню", "menu")])
    return Reply(text="\n".join(lines), keyboard=rows)


def station_view(store, p, station):
    """Список рецептов станка."""
    icon, name = data.STATIONS.get(station, ("🔨", "Кузница"))
    idxs = recipes_for(station)
    lines = [f"{icon} <b>{name}</b>", f"🪙 <b>{p.gold}</b>", ""]
    rows, row = [], []
    from engine import itemui
    for n, i in enumerate(idxs, 1):
        rname, ricon, _st, _idx, need, price, lvl = recipe(i)
        ok, why = can_craft(store, p, i)
        mark = "✅" if ok else "🚫"
        parts = " + ".join(material_line(m, c) for m, c in need.items())
        lines.append(f"{itemui.digit(n)} {ricon} <b>{rname}</b> · {price}🪙 · ур.{lvl} {mark}")
        lines.append(f"     {parts}" + ("" if ok else f" · <i>{why}</i>"))
        row.append((f"{itemui.digit(n)}{ricon}", f"mk:{i}"))
        if len(row) == itemui.PER_ROW:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    if not idxs:
        lines.append("<i>Здесь пока нечего ковать.</i>")
    lines.append("")
    lines.append("<i>Нажми номер — изготовлю, если хватит материалов.</i>")
    rows.append([("◀️ В мастерскую", "craft")])
    return Reply(text="\n".join(lines), keyboard=rows)


def sharpen_view(store, p, page=0):
    """Список своих именных вещей под заточку."""
    from engine import itemui
    mine = [i for i in items.owned_by(store, p.tg_id)
            if int(i.get("upgrade") or 0) < data.MAX_UPGRADE]
    if not mine:
        return Reply(text=("⚡ <b>Заточка</b>\n\n<i>Нет именных вещей. "
                           "Они появляются из боя, сундуков и кузницы.</i>"),
                     keyboard=[[("◀️ В мастерскую", "craft")]])
    entries, page = itemui.slice_page(mine, page)
    lines = ["⚡ <b>Заточка</b>", f"🪙 <b>{p.gold}</b>", ""]
    rows, row = [], []
    for num, _pos, inst in entries:
        cost = upgrade_price(inst)
        chance, _m = upgrade_odds(int(inst.get("upgrade") or 0))
        lines.append(f"{itemui.digit(num)} {inst['icon']} <b>{items.title(inst)}</b>")
        lines.append(f"     {items.tag(inst)} · {cost}🪙 · шанс {int(chance * 100)}%")
        row.append((f"{itemui.digit(num)}{inst['icon']}", f"shrp:{inst['uid']}"))
        if len(row) == itemui.PER_ROW:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows += itemui.pager(page, len(mine), "sharpen")
    rows.append([("◀️ В мастерскую", "craft")])
    lines.append("")
    lines.append("<i>Неудача не ломает вещь — теряется только плата.</i>")
    return Reply(text="\n".join(lines), keyboard=rows)
