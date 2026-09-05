"""Дом героя: якорь, сундук и отдых у очага (IDEAS-next, пункт 8).

Чем дом отличается от защищённого кармана (engine/stash.py): карман дают
всем и он открывает руки в любых безопасных землях — зато вмещает горстку.
Дом покупается один раз, хранит на порядок больше, но и доступ к нему
домашний: сундук привязан к поселению, где герой осел, и открыть его
можно только стоя у своих дверей. В этом и смысл «якоря»: трофеи нужно
куда-то нести, а дорога домой — это план на вечер.

Числа здесь — единый источник для обоих стеков: core/homestead.py
импортирует RULES, поэтому цены и лечение не разъедутся (тот же приём,
что у осад: engine/siege.py).
"""
from engine.models import Reply

RULES = {
    # уровень -> цена въезда/надстройки в бронзе и ячеек сундука.
    # 0-й уровень — дома нет: ночуем у костра на общих условиях.
    "cost": {1: 1500, 2: 6000, 3: 15000},
    "slots": {1: 12, 2: 24, 3: 40},
    "vip_bonus": 12,            # 👑 второй этаж
    "rest_share": {1: 0.5, 2: 2 / 3, 3: 1.0},   # доля HP/MP у очага
    "camp_share": 1 / 3,        #   у костра — как всегда
    "max_level": 3,
}

LEVEL_TITLES = {1: "🛖 Избушка", 2: "🏠 Дом", 3: "🏰 Палаты"}


# ── чистые правила (примитивы — их переиспользует сервер) ──

def capacity(level: int, vip: bool = False) -> int:
    base = RULES["slots"].get(int(level), 0)
    return base + (RULES["vip_bonus"] if base and vip else 0)


def upgrade_cost(level: int):
    """Сколько стоит следующий уровень; None — выше только небо."""
    nxt = int(level) + 1
    return RULES["cost"].get(nxt) if nxt <= RULES["max_level"] else None


def rest_share(level: int, at_home: bool, vip: bool = False) -> float:
    if not at_home or int(level) <= 0:
        return RULES["camp_share"]
    return 1.0 if vip else RULES["rest_share"].get(int(level), RULES["camp_share"])


def rest_amount(max_value: int, share: float) -> int:
    """Сколько восстановить. У костра — прежнее целочисленное деление,
    чтобы правка не поменяла ни одного старого боя; дома — по доле."""
    if share <= RULES["camp_share"] + 1e-9:
        return max(1, int(max_value) // 3)
    return max(1, min(int(max_value), int(round(int(max_value) * share))))


# ── браузерный герой ───────────────────────────────────────

def settled(p) -> bool:
    return int(getattr(p, "house_level", 0) or 0) > 0


def home_loc(p) -> int:
    # именно `is None`, а не `or -1`: нулевая локация — жилая
    raw = getattr(p, "home_loc", -1)
    return -1 if raw is None else int(raw)


def at_home(p) -> bool:
    """Дома ли герой: дом привязан к локации, где он осел."""
    return settled(p) and home_loc(p) == int(p.loc)


def is_vip(p) -> bool:
    """VIP считаем так же, как у кармана: второй этаж — его привилегия."""
    from engine import stash
    return stash.is_vip(p)


def cap_of(p) -> int:
    return capacity(int(p.house_level or 0) if settled(p) else 0, is_vip(p))


def free(p) -> int:
    return max(0, cap_of(p) - len(_chest(p)))


def can_put(p) -> bool:
    """Кнопка «убрать домой» на карточке вещи: только стоя у своих дверей."""
    return at_home(p) and free(p) > 0


def safe_here(p):
    from engine import stash
    return stash.safe_here(p)


def _chest(p):
    lst = getattr(p, "home", None)
    if not isinstance(lst, list):
        lst = []
        p.home = lst
    return lst


# ── действия ────────────────────────────────────────────────

def settle(p, store):
    """Осесть: одна бронза, и у героя появляется адрес."""
    from engine import currency
    if settled(p):
        return Reply(alert="Дом у тебя уже есть — загляни в него.")
    if not safe_here(p):
        return Reply(alert="Оситься можно только в безопасных землях. "
                           "Погост подойдёт.")
    cost = RULES["cost"][1]
    if not currency.deduct_currency(p, cost):
        return Reply(alert=f"На въезд не хватает: нужно {cost}🟤.")
    p.house_level = 1
    p.home_loc = int(p.loc)
    _save(store, p)
    r = screen(store, p)
    r.alert = "🏠 Ты осел. Сундук переживёт что угодно — дома."
    return r


def upgrade(p, store):
    from engine import currency
    if not settled(p):
        return Reply(alert="Сначала оседляйся.")
    cost = upgrade_cost(p.house_level)
    if cost is None:
        return Reply(alert="Дальше только башня. Это предел.")
    if not currency.deduct_currency(p, cost):
        return Reply(alert=f"На надстройку нужно {cost}🟤.")
    p.house_level = int(p.house_level) + 1
    _save(store, p)
    r = screen(store, p)
    r.alert = f"⬆️ {LEVEL_TITLES[p.house_level]} — места больше!"
    return r


def put(p, pos, store=None):
    """Сумка → домашний сундук. Только дома, иначе это был бы карман."""
    from engine import slots
    if not at_home(p):
        return Reply(alert="Сундук стоит дома — зайди в свои двери.")
    if free(p) <= 0:
        return Reply(alert=f"Сундук полон: {cap_of(p)} ячеек.")
    pos = int(pos)
    if pos < 0 or pos >= len(p.inventory):
        return Reply(alert="Предмет не найден.")
    idx = slots.take_at(p, pos)
    _chest(p).append(idx)
    if store is not None:
        _save(store, p)
    from engine import rules
    return Reply(alert=f"🏠 В сундук: {rules.item(idx)['name']}")


def take(p, pos, store=None):
    """Сундук → сумка."""
    if not at_home(p):
        return Reply(alert="Сундук дома — там и открывают.")
    pos = int(pos)
    chest = _chest(p)
    if pos < 0 or pos >= len(chest):
        return Reply(alert="Такой вещи в сундуке нет.")
    from engine import rules
    idx = chest.pop(pos)
    p.inventory.append(idx)
    if store is not None:
        _save(store, p)
    return Reply(alert=f"🎒 В сумке снова: {rules.item(idx)['name']}")


def _save(store, p):
    if store is not None:
        store.save_player(p)


def rest_note(p) -> str:
    """Строчка для экрана отдыха: очаг или костёр."""
    return ("<i>🔥 Дом отдыхает лучше каменных стен: лечит сильнее.</i>"
            if at_home(p) else "")


# ── витрина браузера ────────────────────────────────────────

def button(store, p, rows):
    """Строка на экран клетки: войти в дом или осесть (как делали осады)."""
    if settled(p) and at_home(p):
        rows.insert(0, [(f"🏠 Дом · сундук {len(_chest(p))}/{cap_of(p)}",
                         "house")])
    elif not settled(p) and safe_here(p):
        rows.insert(0, [(f"🏠 Оселиться здесь ({RULES['cost'][1]}🟤)",
                         "house:buy")])


def screen(store, p):
    from engine import itemui, rules
    if not settled(p):
        lines = ["🏠 <b>Дом героя</b>", "",
                 "Своего порога у тебя пока нет.",
                 "<i>Оситься можно в безопасных землях: сундук переживёт"
                 " смерть, отдых у очага лечит сильнее, а соседей по"
                 " поселению видно каждый день.</i>"]
        rows = []
        if safe_here(p):
            rows.append([(f"🏠 Оселиться ({RULES['cost'][1]}🟤)", "house:buy")])
        rows.append([("◀️ В мир", "world")])
        return Reply(text="\n".join(lines), keyboard=rows)

    level = int(p.house_level)
    cap = cap_of(p)
    chest = _chest(p)
    lines = [f"{LEVEL_TITLES.get(level, '🏠 Дом')} <b>Дом героя</b>", "",
             f"📦 Сундук: <b>{len(chest)}/{cap}</b>"
             + (f" · 👑 второй этаж +{RULES['vip_bonus']}" if is_vip(p) else "")]
    note = upgrade_cost(level)
    lines.append(f"⬆️ Надстройка: <b>{note}🟤</b>" if note
                 else "⬆️ Выше только звёзды — это предел.")
    lines.append("")
    if chest:
        for n, idx in enumerate(chest, 1):
            lines.append(itemui.line(n, idx, itemui.type_label(rules.item(idx))))
        lines.append("<i>Нажми номер, чтобы вернуть вещь в сумку.</i>")
    else:
        lines.append("<i>Сундук пуст. Всё, что здесь ляжет, — переживёт всё.</i>")

    entries = [(n, n - 1, idx) for n, idx in enumerate(chest, 1)]
    rows = itemui.grid(entries, "house:take") if entries else []
    if note:
        rows.append([(f"⬆️ Надстроить ({note}🟤)", "house:up")])
    rows.append([("🏕 Отдых у очага", "rest")])
    rows.append([("◀️ В мир", "world")])
    return Reply(text="\n".join(lines), keyboard=rows)


def play(store, p, arg=""):
    """Единая точка входа колбэков «house:*» (роутер game.py)."""
    if arg == "buy":
        return settle(p, store)
    if arg == "up":
        return upgrade(p, store)
    if arg.startswith("put:"):
        put(p, arg[4:], store=store)
        return screen(store, p)
    if arg.startswith("take:"):
        take(p, arg[5:], store=store)
        return screen(store, p)
    return screen(store, p)
