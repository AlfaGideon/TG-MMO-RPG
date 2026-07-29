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

SLOTS = 5                    # базовый размер защищённого кармана
VIP_BONUS = 3                # сколько ячеек добавляет VIP
LOSS_SHARE = 0.5             # какая доля сумки выпадает при гибели
SAFE_TYPES = ("safe",)       # где можно перекладывать


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


def revoke_vip(p):
    p.is_vip = False
    p.vip_until = 0.0


# ── размер кармана ──────────────────────────────────────────

def capacity(p):
    """Сколько ячеек в защищённом кармане у этого героя."""
    return SLOTS + (VIP_BONUS if is_vip(p) else 0)


def free_slots(p):
    return max(0, capacity(p) - len(getattr(p, "stash", None) or []))


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

def put(p, arg):
    """Убрать предмет из сумки в защищённый карман."""
    if not safe_here(p):
        return _need_safe()
    pos = int(arg)
    if pos >= len(p.inventory):
        return Reply(alert="Предмет не найден.")
    if free_slots(p) <= 0:
        return Reply(alert=f"Карман полон: {capacity(p)} ячеек. "
                           f"Освободи место или расширь VIP-статусом.")
    idx = p.inventory.pop(pos)
    it = rules.item(idx)
    if p.equipped.get(it["type"]) == idx:     # спрятанное нельзя носить
        p.equipped.pop(it["type"], None)
    _stash(p).append(idx)
    r = view(p)
    r.alert = f"🔒 В карман: {it['name']}"
    return r


def take(p, arg):
    """Достать предмет из кармана обратно в сумку."""
    if not safe_here(p):
        return _need_safe()
    pos = int(arg)
    lst = _stash(p)
    if pos >= len(lst):
        return Reply(alert="Предмет не найден.")
    idx = lst.pop(pos)
    p.inventory.append(idx)
    r = view(p)
    r.alert = f"🎒 В сумку: {rules.item(idx)['name']}"
    return r


# ── потери при гибели ───────────────────────────────────────

def drop_on_death(p, rng=None):
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
    count = max(1, int(len(losable) * LOSS_SHARE))
    lost_pos = sorted(rng.sample(losable, min(count, len(losable))), reverse=True)
    lost = []
    for pos in lost_pos:
        lost.append(p.inventory.pop(pos))
    return lost


# ── экраны ──────────────────────────────────────────────────

def view(p, page=0):
    """Экран кармана: что защищено, что можно убрать, сколько места."""
    lst = _stash(p)
    cap = capacity(p)
    vip_note = ""
    if is_vip(p):
        days = vip_left_days(p)
        vip_note = (f" · 👑 VIP +{VIP_BONUS}"
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
        lines.append(f"<i>👑 VIP расширяет карман до {SLOTS + VIP_BONUS} ячеек.</i>")

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
