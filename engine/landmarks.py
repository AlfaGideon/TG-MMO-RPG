"""Достопримечательности: знание мира становится ценностью.

В `data.STORIES` уже лежало 40 описаний клеток — «Древний менгир», «Скала с
рунами», «Заброшенный колодец». Они были чистой декорацией: игрок читал
текст и шёл дальше.

Теперь часть из них — объекты с однократной наградой. Клетка узнаётся по
имени (`Cell.name`), поэтому новое поле в модели не понадобилось, а старые
миры получают достопримечательности автоматически.

Награда выдаётся один раз на героя: список посещённого лежит в
`p.landmarks`. Это и есть смысл разведки — карта перестаёт быть просто
серым туманом.
"""
import random

from engine import factions, items, rules
from engine.models import Reply

# имя клетки -> (значок, что даёт, текст находки)
#   gold  — монеты, размер зависит от уровня героя;
#   item  — предмет из data.ITEMS по индексу;
#   heal  — полное восстановление сил;
#   exp   — опыт;
#   magic — разовое благословение: +1 к случайному стату навсегда.
LANDMARKS = {
    "Древний менгир": ("🗿", "magic",
                       "Камень тёплый на ощупь. Ладонь покалывает — и что-то "
                       "внутри тебя меняется навсегда."),
    "Скала с рунами": ("🪧", "exp",
                       "Ты разбираешь древние знаки. Знание оседает в памяти."),
    "Заброшенный колодец": ("🪣", "gold",
                            "На дне блестит монета. За ней — ещё горсть."),
    "Заросший колодец": ("🪣", "gold",
                         "Под плющом кто-то спрятал кошель. Теперь он твой."),
    "Ветхая часовня": ("⛪", "heal",
                       "Алтарь цел. Ты преклоняешь колено — и усталость уходит."),
    "Каменный идол": ("🗿", "magic",
                      "Безликий бог смотрит сквозь тебя. Дар остаётся в крови."),
    "Дупло с сокровищем": ("🌳", "item",
                           "В дупле блестит свёрток. Кто-то прятал это давно."),
    "Разбитый обоз": ("🛒", "item",
                      "Среди обломков уцелел ящик с добром."),
    "Заброшенная мельница": ("🏚", "gold",
                             "Под жерновом — тайник мельника."),
    "Поляна с травами": ("🌿", "heal",
                         "Ты жуёшь горький лист. По телу разливается тепло."),
    "Скопление грибов": ("🍄", "exp",
                         "Светящиеся грибы складываются в узор. Ты запоминаешь его."),
    "Поваленная статуя": ("🗿", "gold",
                          "В основании статуи — полость с королевской казной."),
    "Гнездо воронов": ("🪶", "item",
                       "Вороны растащили чужое добро. Кое-что осталось."),
    "Склеп под корнями": ("⚰️", "item",
                          "Плита поддаётся. Внутри — дар мертвецу, ему не нужный."),
    "Тёмная заводь": ("💧", "magic",
                      "Отражение в воде — не твоё. Оно улыбается и дарит силу."),
}

STATS = ("strength", "agility", "intelligence", "endurance", "luck")
SEEN = "landmarks"          # поле игрока со списком посещённого


def of(cell, store=None):
    """Достопримечательность этой клетки или None.

    Названия из `STORIES` повторяются десятками — если считать диковиной
    каждую «Тёмную заводь», их будут сотни и ценность пропадёт. Поэтому
    настоящая диковина — только **первая** клетка такого имени в локации
    (со `store`); без хранилища работает быстрая проверка по имени.
    """
    if cell is None:
        return None
    row = LANDMARKS.get(cell.name)
    if row is None:
        return None
    if store is not None and cell.key not in keys(store):
        return None
    icon, kind, text = row
    return {"name": cell.name, "icon": icon, "kind": kind, "text": text}


def _seen(p):
    lst = getattr(p, SEEN, None)
    if not isinstance(lst, list):
        lst = []
        setattr(p, SEEN, lst)
    return lst


def visited(p, cell):
    """Уже забирал награду с этой клетки?"""
    return cell is not None and cell.key in _seen(p)


def total(store, p=None):
    """Сколько достопримечательностей в мире и сколько найдено героем."""
    ks = keys(store)
    seen = set(_seen(p)) if p is not None else set()
    return len(ks & seen), len(ks)


def keys(store):
    """Ключи настоящих диковин: по одной каждого вида на локацию.

    Выбор устойчив (первая по координатам), поэтому набор не «плавает»
    между вызовами и после перезагрузки мира.
    """
    best = {}
    for c in store.world.values():
        if c.name not in LANDMARKS or not c.passable:
            continue
        slot = (c.loc, c.name)
        if slot not in best or (c.x, c.y) < (best[slot].x, best[slot].y):
            best[slot] = c
    return {c.key for c in best.values()}


# ── награда ─────────────────────────────────────────────────

def claim(store, p, cell, rng=None):
    """Забрать награду достопримечательности. Один раз на героя."""
    mark = of(cell, store)
    if mark is None:
        return Reply(alert="Здесь нет ничего примечательного.")
    if visited(p, cell):
        return Reply(alert="Ты уже брал здесь всё, что было.")
    rng = rng or random
    _seen(p).append(cell.key)

    lines = [f"{mark['icon']} <b>{cell.name}</b>", "", f"<i>{mark['text']}</i>", ""]
    kind = mark["kind"]

    if kind == "gold":
        gold = rng.randint(20, 40) + p.level * 10
        p.gold += gold
        lines.append(f"💰 Найдено: <b>{gold}</b> 🪙")
    elif kind == "exp":
        exp = 40 + p.level * 20
        levels = rules.add_exp(p, exp)
        lines.append(f"⭐ Опыт: <b>+{exp}</b>")
        if levels:
            lines.append(f"🎖 <b>Новый уровень: {p.level}!</b>")
    elif kind == "heal":
        s = rules.stats(p, store)
        p.hp, p.mp = s["max_hp"], s["max_mp"]
        from engine import death
        death.heal_wounds(p)
        lines.append("❤️ Силы полностью восстановлены, раны затянулись.")
    elif kind == "magic":
        stat = rng.choice(STATS)
        setattr(p, stat, getattr(p, stat, 10) + 1)
        label = {"strength": "💪 Сила", "agility": "🏃 Ловкость",
                 "intelligence": "🧠 Интеллект", "endurance": "🧱 Выносливость",
                 "luck": "🍀 Удача"}[stat]
        lines.append(f"✨ Благословение навсегда: <b>{label} +1</b>")
    else:                                       # item
        idx = _pick_item(p, rng)
        p.inventory.append(idx)
        inst = items.create(store, idx, source="chest", owner=p.tg_id,
                            luck=p.luck, detail=cell.name)
        it = rules.item(idx)
        if inst is not None:
            lines.append(f"📦 Находка: {inst['icon']} <b>{items.title(inst)}</b>")
        else:
            lines.append(f"📦 Находка: {it['icon']} {it['name']}")

    lines.extend(factions.award(store, p, "landmark_found"))
    found, all_ = total(store, p)
    lines.append(f"\n🗺 Достопримечательностей: <b>{found}/{all_}</b>")
    store.save_player(p)
    return Reply(text="\n".join(lines), keyboard=[[("◀️ В мир", "world")]])


def _pick_item(p, rng):
    """Находка по уровню героя: чем выше, тем дороже может попасться."""
    from engine import data

    pool = [i for i, it in enumerate(data.ITEMS) if it[3] <= 30 + p.level * 25]
    return rng.choice(pool or range(len(data.ITEMS)))


def note(p, cell, store=None):
    """Строка для осмотра клетки: есть ли тут что-то и брал ли игрок."""
    mark = of(cell, store)
    if mark is None:
        return ""
    if visited(p, cell):
        return f"{mark['icon']} {cell.name} — уже осмотрено"
    return f"{mark['icon']} <b>{cell.name}</b> — здесь что-то есть!"
