"""Уникальные экземпляры предметов: свой ID, свои статы, своя летопись.

Предмет в `data.ITEMS` — это *шаблон*. Каждый выпавший, купленный или
скрафченный экземпляр — отдельная запись со своим коротким ID и
собственными статами, откатанными с разбросом от шаблона. Поэтому два
«Ржавых меча» никогда не одинаковы.

Перед ID стоит значок способа получения (`⚔️IT-D55CA5C1`), поэтому
происхождение вещи видно с одного взгляда.

Реестр живёт в настройках Store, значит его видят и бот, и панель.
Расходники и материалы не катаются — они складываются в стопки.
"""
import random
import time

from engine import data, money, rules

KEY = "instances"           # реестр экземпляров в store.settings
LIMIT = 600                 # сколько экземпляров храним (старые вытесняются)

# Метки, которые важнее исходного источника при выборе значка
PRIORITY = ("unique", "festive", "auction")

STACKABLE = ("consumable",)


# ── реестр ──────────────────────────────────────────────────

def registry(store):
    """{uid: экземпляр}. Создаётся лениво."""
    reg = store.settings.get(KEY)
    if not isinstance(reg, dict):
        reg = {}
        store.settings[KEY] = reg
    return reg


def all_instances(store):
    """Все экземпляры от новых к старым."""
    return sorted(registry(store).values(),
                  key=lambda i: i.get("ts", 0), reverse=True)


def get(store, uid):
    return registry(store).get(str(uid))


def owned_by(store, tg_id):
    """Именные вещи конкретного игрока."""
    return [i for i in all_instances(store) if int(i.get("owner") or 0) == int(tg_id)]


def new_uid():
    """Короткий человекочитаемый ID экземпляра."""
    try:
        import secrets
        tail = secrets.token_hex(4).upper()
    except Exception:                                      # pragma: no cover
        tail = "".join(random.choice("0123456789ABCDEF") for _ in range(8))
    return "IT-" + tail


# ── броски ──────────────────────────────────────────────────

def roll_quality(variance=0.15, luck=0):
    """Качество в процентах от базы. Треугольное: середина вероятнее краёв."""
    variance = max(0.0, min(0.6, float(variance)))
    spread = int(round(variance * 100))
    if spread <= 0:
        return 100
    base = random.triangular(100 - spread, 100 + spread, 100)
    base += min(10, luck * 0.25)
    return max(40, min(200, int(round(base))))


def roll_rarity(base, luck=0):
    """Небольшой шанс получить ступень выше шаблонной."""
    order = data.RARITY_ORDER
    if base not in order:
        return base
    i = order.index(base)
    if i >= len(order) - 1:
        return base
    chance = 0.06 + min(0.10, luck / 400)
    return order[i + 1] if random.random() < chance else base


def prefix_for(quality):
    for threshold, names in data.QUALITY_PREFIXES:
        if quality <= threshold:
            return random.choice(names)
    return ""


def roll_stats(idx, quality, rarity):
    """Статы экземпляра: база × качество × редкость + джиттер ±6 % на стат."""
    mult = data.RARITY_MULT.get(rarity, 1.0) * (quality / 100.0)
    out = {}
    for key, val in rules.item(idx)["bonus"].items():
        jitter = random.uniform(0.94, 1.06)
        rolled = int(round(val * mult * jitter))
        out[key] = max(1, rolled) if val > 0 else rolled
    return out


def stackable(idx):
    return rules.item(idx)["type"] in STACKABLE


# ── создание ────────────────────────────────────────────────

def create(store, idx, source="mob", owner=0, luck=0, detail="", quality=None):
    """Новый экземпляр шаблона `idx`. Возвращает запись или None для стопок."""
    idx = int(idx)
    if not 0 <= idx < len(data.ITEMS) or stackable(idx):
        return None

    tpl = rules.item(idx)
    q = roll_quality(0.15, luck) if quality is None else int(quality)
    rarity = roll_rarity(tpl["rarity"], luck)
    inst = {
        "uid": new_uid(),
        "idx": idx,
        "name": tpl["name"],
        "prefix": prefix_for(q),
        "icon": tpl["icon"],
        "type": tpl["type"],
        "rarity": rarity,
        "quality": q,
        "stats": roll_stats(idx, q, rarity),
        "source": source if source in data.SOURCES else "mob",
        "owner": int(owner or 0),
        "upgrade": 0,
        "trades": 0,
        "festive": source == "festive",
        "unique": source == "unique",
        "ts": int(time.time()),
        "log": [],
    }
    reg = registry(store)
    reg[inst["uid"]] = inst
    _trim(reg)
    event = data.SOURCE_EVENTS.get(inst["source"], "created")
    record(store, inst, event, owner, detail)
    return inst


def _trim(reg):
    """Держим реестр в разумном размере: вытесняем самые старые."""
    if len(reg) <= LIMIT:
        return
    old = sorted(reg.values(), key=lambda i: i.get("ts", 0))[:len(reg) - LIMIT]
    for i in old:
        reg.pop(i["uid"], None)


# ── летопись ────────────────────────────────────────────────

def record(store, inst, event, who=0, detail="", price=0):
    """Дописывает строку в историю экземпляра."""
    if not inst:
        return
    name = ""
    p = store.players.get(int(who or 0))
    if p is not None:
        name = p.name
    inst.setdefault("log", []).append({
        "ts": int(time.time()), "event": str(event), "who": int(who or 0),
        "name": name, "detail": str(detail), "price": int(price or 0),
    })
    inst["log"] = inst["log"][-30:]


def history(inst):
    """Летопись строками для показа игроку и админу."""
    out = []
    for e in inst.get("log", []):
        icon, label = data.EVENTS.get(e.get("event"), ("•", e.get("event", "")))
        when = stamp(e.get("ts", 0))
        who = f" — {e['name']}" if e.get("name") else ""
        price = f" за {money.fmt(e['price'])}" if e.get("price") else ""
        detail = f" ({e['detail']})" if e.get("detail") else ""
        out.append(f"{icon} {when} {label}{who}{price}{detail}")
    return out


def stamp(ts, fmt="%d.%m %H:%M"):
    try:
        return time.strftime(fmt, time.localtime(int(ts)))
    except Exception:                                      # pragma: no cover
        return "—"


# ── отображение ─────────────────────────────────────────────

def badge(inst):
    """Значок способа получения. Особые метки важнее исходного источника."""
    if inst.get("unique"):
        return data.SOURCES["unique"][0]
    if inst.get("festive"):
        return data.SOURCES["festive"][0]
    if int(inst.get("trades") or 0) > 0:
        return data.SOURCES["auction"][0]
    return data.SOURCES.get(inst.get("source"), ("🔹", ""))[0]


def tag(inst):
    """Строка вида ⚔️IT-D55CA5C1 — значок происхождения плюс ID."""
    return f"{badge(inst)}{inst.get('uid', '')}"


def title(inst):
    """Полное имя: префикс качества, название, значок заточки."""
    parts = []
    if inst.get("prefix"):
        parts.append(inst["prefix"])
    parts.append(inst.get("name", "?"))
    name = " ".join(parts)
    up = int(inst.get("upgrade") or 0)
    return f"{name} +{up}" if up else name


def source_label(inst):
    return data.SOURCES.get(inst.get("source"), ("", "Неизвестно"))[1]


def price(inst):
    """Оценка экземпляра: база шаблона с учётом качества, редкости и заточки."""
    idx = int(inst.get("idx", 0))
    base = rules.item(idx)["price"] if 0 <= idx < len(data.ITEMS) else 10
    mult = data.RARITY_MULT.get(inst.get("rarity"), 1.0)
    val = base * mult * (int(inst.get("quality") or 100) / 100.0)
    val *= 1 + 0.35 * int(inst.get("upgrade") or 0)
    val *= 1 + 0.05 * min(5, int(inst.get("trades") or 0))
    if inst.get("unique"):
        val *= 5
    elif inst.get("festive"):
        val *= 1.5
    return max(1, int(round(val)))


def stats_line(inst):
    """Бонусы экземпляра одной строкой."""
    from engine import itemui
    out = []
    for k, v in (inst.get("stats") or {}).items():
        icon, label = itemui.BONUS.get(k, ("•", k))
        out.append(f"{icon} {label} +{v}")
    return " · ".join(out) or "без бонусов"


# ── передача и продажа ──────────────────────────────────────

def transfer(store, inst, new_owner, event="sold", price_paid=0):
    """Смена владельца с записью в летопись."""
    inst["owner"] = int(new_owner or 0)
    if event == "sold":
        inst["trades"] = int(inst.get("trades") or 0) + 1
    record(store, inst, event, new_owner, price=price_paid)
    return inst


def destroy(store, uid):
    return registry(store).pop(str(uid), None)


def drop_one(store, tg_id, idx):
    """Убирает у игрока самый старый экземпляр шаблона (при продаже)."""
    mine = [i for i in owned_by(store, tg_id) if int(i.get("idx", -1)) == int(idx)]
    if not mine:
        return None
    inst = mine[-1]
    inst["owner"] = 0
    return inst


def stats(store):
    """Сводка для панели."""
    reg = registry(store)
    vals = list(reg.values())
    return {
        "total": len(vals),
        "unique": sum(1 for i in vals if i.get("unique")),
        "festive": sum(1 for i in vals if i.get("festive")),
        "traded": sum(1 for i in vals if int(i.get("trades") or 0) > 0),
        "upgraded": sum(1 for i in vals if int(i.get("upgrade") or 0) > 0),
        "owned": sum(1 for i in vals if int(i.get("owner") or 0)),
    }
