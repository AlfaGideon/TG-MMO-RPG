"""Два инвентаря: сумка теряется при смерти, защищённый карман — нет.

Как в Таркове: игрок сам решает, что взять «в рейд» риском, а что убрать
в безопасное место. Карман намеренно **меньше** сумки — иначе выбора нет,
все бы просто прятали всё.

  🎒 **Сумка** (`p.inventory`) — безразмерная, но при гибели часть вещей
     выпадает в надгробие вместе с золотом.
  🔒 **Карман** (`p.stash`) — вмещает `SLOTS` предметов, при смерти цел.
     VIP расширяет его на `VIP_BONUS` ячеек — это удобство, а не сила:
     карман не даёт статов и не влияет на бой.

Перекладывать можно только в безопасной локации: иначе игрок прятал бы
добычу прямо перед смертью и риск исчезал бы.
"""
import time

from engine import data, itemui, rules
from engine.models import Reply

# Значения по умолчанию. Живые настройки лежат в settings и правятся из
# панели — см. tune(); константы остаются запасным вариантом, когда store
# недоступен (например, в чистых расчётах и тестах движка).
SLOTS = 5                    # базовый размер защищённого кармана
VIP_BONUS = 3                # сколько ячеек добавляет VIP
LOSS_SHARE = 0.5             # какая доля сумки выпадает при гибели
VIP_DAYS = 30                # срок VIP по умолчанию при выдаче из панели
SAFE_TYPES = ("safe",)       # где можно перекладывать

# ключ настройки -> (значение по умолчанию, подпись, пояснение)
TUNABLES = {
    "stash_slots": (SLOTS, "🔒 Ячеек в кармане",
                    "сколько вещей переживает гибель у обычного героя"),
    "stash_vip_bonus": (VIP_BONUS, "👑 Прибавка VIP",
                        "на сколько ячеек VIP расширяет карман"),
    "stash_loss_share": (LOSS_SHARE, "💀 Доля потерь сумки",
                         "какая часть сумки выпадает при смерти (0–1)"),
    "vip_days": (VIP_DAYS, "📅 Срок VIP, дней",
                 "на сколько дней выдаётся VIP кнопкой в панели"),
}


def tune(store, key):
    """Настройка из панели или значение по умолчанию."""
    default = TUNABLES[key][0]
    if store is None:
        return default
    raw = store.settings.get(key)
    if raw is None or raw == "":
        return default
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return default
    if key == "stash_loss_share":
        return max(0.0, min(1.0, val))
    return max(0, int(val))


def set_tunables(store, values):
    """Сохранить настройки кармана и VIP. Пустое — вернуть умолчание."""
    for key in TUNABLES:
        if key not in values:
            continue
        raw = values[key]
        if raw is None or str(raw).strip() == "":
            store.settings.pop(key, None)
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        if key == "stash_loss_share":
            store.settings[key] = max(0.0, min(1.0, val))
        else:
            store.settings[key] = max(0, int(val))
    store.save()


# ── VIP ─────────────────────────────────────────────────────

def is_vip(p):
    """Активен ли VIP: бессрочный или ещё не истёкший."""
    if not getattr(p, "is_vip", False):
        return False
    until = float(getattr(p, "vip_until", 0) or 0)
    return until <= 0 or time.time() < until


def vip_left_days(p):
    until = float(getattr(p, "vip_until", 0) or 0)
    if not is_vip(p) or until <= 0:
        return 0
    return max(0, int((until - time.time()) // 86400) + 1)


def grant_vip(p, days=0):
    """Выдать VIP. days=0 — бессрочно."""
    p.is_vip = True
    p.vip_until = (time.time() + days * 86400) if days else 0.0


def vip_days(store):
    """Срок VIP при выдаче из панели."""
    return tune(store, "vip_days")


def revoke_vip(p):
    p.is_vip = False
    p.vip_until = 0.0
    p.offline_protected = False


def offline_protected(p):
    """Полная защита VIP от игровых воздействий на время выхода."""
    return is_vip(p) and bool(getattr(p, "offline_protected", False))


def set_offline(p, enabled):
    if enabled and not is_vip(p):
        return False, "Режим «Я офлайн» доступен только VIP."
    if enabled and p.combat:
        return False, "Сначала закончи бой."
    p.offline_protected = bool(enabled)
    return True, ("Ты офлайн. VIP-защита включена." if enabled
                  else "Ты снова в мире.")


# ── размер кармана ──────────────────────────────────────────

def capacity(p, store=None):
    """Сколько ячеек в защищённом кармане у этого героя.

    `store` необязателен: без него берутся значения по умолчанию, поэтому
    старые вызовы продолжают работать.
    """
    base = tune(store, "stash_slots")
    return base + (tune(store, "stash_vip_bonus") if is_vip(p) else 0)


def free_slots(p, store=None):
    return max(0, capacity(p, store) - len(getattr(p, "stash", None) or []))


def _stash(p):
    lst = getattr(p, "stash", None)
    if not isinstance(lst, list):
        lst = []
        p.stash = lst
    return lst


# ── где можно перекладывать ─────────────────────────────────

def safe_here(p):
    """Можно ли сейчас трогать карман: только в безопасных землях."""
    if p.loc >= len(data.LOCATIONS):
        return False
    return data.LOCATIONS[p.loc][2] in SAFE_TYPES


def _need_safe():
    return Reply(alert="Карман открывается только в безопасных землях — "
                       "загляни в Погост.")


# ── перекладывание ──────────────────────────────────────────

def put(p, arg, store=None):
    """Убрать предмет из сумки в защищённый карман."""
    if not safe_here(p):
        return _need_safe()
    pos = int(arg)
    if pos >= len(p.inventory):
        return Reply(alert="Предмет не найден.")
    if free_slots(p, store) <= 0:
        return Reply(alert=f"Карман полон: {capacity(p, store)} ячеек. "
                           f"Освободи место или расширь VIP-статусом.")
    idx = p.inventory.pop(pos)
    it = rules.item(idx)
    if p.equipped.get(it["type"]) == idx:     # спрятанное нельзя носить
        p.equipped.pop(it["type"], None)
    _stash(p).append(idx)
    r = view(p, store=store)
    r.alert = f"🔒 В карман: {it['name']}"
    return r


def take(p, arg, store=None):
    """Достать предмет из кармана обратно в сумку."""
    if not safe_here(p):
        return _need_safe()
    pos = int(arg)
    lst = _stash(p)
    if pos >= len(lst):
        return Reply(alert="Предмет не найден.")
    idx = lst.pop(pos)
    p.inventory.append(idx)
    r = view(p, store=store)
    r.alert = f"🎒 В сумку: {rules.item(idx)['name']}"
    return r


# ── потери при гибели ───────────────────────────────────────

def drop_on_death(p, rng=None, store=None):
    """Что выпадает из сумки при смерти. Возвращает список индексов.

    Карман не трогаем — в этом весь смысл. Надетое тоже остаётся: снимать
    с трупа собственную экипировку было бы слишком жестоко для казуальной
    игры, а риск и так есть.
    """
    import random

    rng = rng or random
    worn = set(p.equipped.values())
    losable = [i for i, idx in enumerate(p.inventory) if idx not in worn]
    if not losable:
        return []
    count = max(1, int(len(losable) * tune(store, "stash_loss_share")))
    lost_pos = sorted(rng.sample(losable, min(count, len(losable))), reverse=True)
    lost = []
    for pos in lost_pos:
        lost.append(p.inventory.pop(pos))
    return lost


# ── экраны ──────────────────────────────────────────────────

def view(p, page=0, store=None):
    """Экран кармана: что защищено, что можно убрать, сколько места."""
    lst = _stash(p)
    cap = capacity(p, store)
    vip_note = ""
    if is_vip(p):
        days = vip_left_days(p)
        vip_note = (f" · 👑 VIP +{tune(store, 'stash_vip_bonus')}"
                    + (f" ({days} дн.)" if days else " (бессрочно)"))

    lines = [f"🔒 <b>Защищённый карман</b> — {len(lst)}/{cap}{vip_note}", ""]
    if lst:
        for n, idx in enumerate(lst, 1):
            lines.append(itemui.line(n, idx, itemui.type_label(rules.item(idx))))
    else:
        lines.append("<i>Пусто. Всё, что здесь лежит, переживёт твою смерть.</i>")

    lines.append("")
    if safe_here(p):
        lines.append("<i>Нажми номер, чтобы достать вещь обратно в сумку.</i>")
    else:
        lines.append("⚠️ <i>Перекладывать можно только в безопасных землях.</i>")
    if not is_vip(p):
        big = tune(store, "stash_slots") + tune(store, "stash_vip_bonus")
        lines.append(f"<i>👑 VIP расширяет карман до {big} ячеек.</i>")

    rows = []
    if safe_here(p) and lst:
        entries = [(n, n - 1, idx) for n, idx in enumerate(lst, 1)]
        rows = itemui.grid(entries, "stake")
    rows.append([("🎒 Сумка", "bag"), ("◀️ Меню", "menu")])
    return Reply(text="\n".join(lines), keyboard=rows)


def death_note(lost, kept):
    """Строка для экрана гибели: что потеряно, что уцелело."""
    parts = []
    if lost:
        names = ", ".join(rules.item(i)["name"] for i in lost[:4])
        more = f" и ещё {len(lost) - 4}" if len(lost) > 4 else ""
        parts.append(f"🎒 Выпало из сумки: <b>{len(lost)}</b> — {names}{more}")
    if kept:
        parts.append(f"🔒 В кармане уцелело: <b>{kept}</b>")
    return "\n".join(parts)
