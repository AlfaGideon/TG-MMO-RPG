"""Общий вид списков предметов: нумерация, сетка кнопок, карточка.

Правило оформления: в списке кнопки несут только эмодзи — номер предмета
и его иконку. Что это за номер, написано в тексте сообщения. Подробности
и действия открываются по нажатию номера.
"""
from engine import data, rules

PER_PAGE = 10                     # ровно столько, сколько цифровых эмодзи
PER_ROW = 5

DIGITS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

TYPES = {
    "weapon": ("⚔️", "Оружие"), "armor": ("🦺", "Броня"),
    "helmet": ("🪖", "Шлем"), "boots": ("👢", "Сапоги"),
    "accessory": ("💍", "Украшение"), "consumable": ("🧪", "Расходник"),
}

RARITY = {
    "common": ("⚪", "Обычный"), "uncommon": ("🟢", "Необычный"),
    "rare": ("🔵", "Редкий"), "epic": ("🟣", "Эпический"),
    "legendary": ("🟠", "Легендарный"),
}

BONUS = {
    "damage": ("⚔️", "Урон"), "defense": ("🛡", "Защита"),
    "hp": ("❤️", "Здоровье"), "mp": ("💙", "Мана"),
    "strength": ("💪", "Сила"), "agility": ("🏃", "Ловкость"),
    "intelligence": ("🧠", "Интеллект"), "endurance": ("🧱", "Выносливость"),
    "luck": ("🍀", "Удача"), "heal": ("❤️", "Лечит"),
    "mana": ("💙", "Даёт маны"),
}


def digit(n):
    """Эмодзи-номер позиции 1..10 (дальше — обычные цифры)."""
    return DIGITS[n - 1] if 1 <= n <= len(DIGITS) else f"{n}\ufe0f\u20e3"


def pages(total):
    return max(1, (total + PER_PAGE - 1) // PER_PAGE)


def clamp(page, total):
    return max(0, min(int(page or 0), pages(total) - 1))


def slice_page(items, page):
    """Кусок списка страницы: [(номер на странице, позиция в списке, элемент)]."""
    page = clamp(page, len(items))
    start = page * PER_PAGE
    chunk = items[start:start + PER_PAGE]
    return [(i + 1, start + i, it) for i, it in enumerate(chunk)], page


def grid(entries, action):
    """Сетка кнопок: только номер и иконка предмета, без подписей."""
    rows, row = [], []
    for num, pos, idx in entries:
        row.append((f"{digit(num)}{rules.item(idx)['icon']}", f"{action}:{pos}"))
        if len(row) == PER_ROW:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return rows


def pager(page, total, action):
    """Строка перелистывания. Пустая, если страница одна."""
    last = pages(total)
    if last <= 1:
        return []
    row = []
    row.append(("⬅️", f"{action}:{page - 1}") if page > 0 else ("▪️", "noop"))
    row.append((f"{page + 1}/{last}", "noop"))
    row.append(("➡️", f"{action}:{page + 1}") if page < last - 1 else ("▪️", "noop"))
    return [row]


def bonus_lines(it):
    out = []
    for k, v in it["bonus"].items():
        icon, label = BONUS.get(k, ("•", k))
        out.append(f"{icon} {label} <b>+{v}</b>")
    return "\n".join(out) or "<i>Без бонусов</i>"


def type_label(it):
    icon, label = TYPES.get(it["type"], ("📦", it["type"]))
    dot, rare = RARITY.get(it["rarity"], ("⚪", it["rarity"]))
    return f"{icon} {label} · {dot} {rare}"


def line(num, idx, note=""):
    """Строка списка в тексте сообщения."""
    it = rules.item(idx)
    tail = f" · {note}" if note else ""
    return f"{digit(num)} {it['icon']} <b>{it['name']}</b>{tail}"


def card(idx, extra=""):
    """Шапка карточки предмета: имя, тип, бонусы."""
    it = rules.item(idx)
    body = (f"{it['icon']} <b>{it['name']}</b>\n"
            f"{type_label(it)}\n\n"
            f"{bonus_lines(it)}")
    return body + (f"\n\n{extra}" if extra else "")


def price_of(idx):
    return rules.item(idx)["price"]


def resale_of(idx):
    return max(1, rules.item(idx)["price"] // 2)


def wearable(it):
    return it["type"] in rules.SLOTS


def stock():
    """Ассортимент лавки — все предметы игры."""
    return list(range(len(data.ITEMS)))
