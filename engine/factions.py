"""Фракции и репутация: мир начинает реагировать на поступки игрока.

Прогресс был только в уровне и вещах — упёршись в потолок, расти некуда.
Теперь у мира четыре силы с противоположными интересами, и выбор стороны
что-то значит.

  🛡 **Стража Погоста** — порядок. Платит за убитую нежить, отдаляет беды.
  💰 **Гильдия падальщиков** — нажива. Ценит добычу и мародёрство, торгует
     дешевле, но Страже это не нравится.
  🌑 **Культ Пожирателя** — тьма. Приближает катаклизмы и щедро платит тем,
     кто помогает им случиться.
  ⚜️ **Орден Рассвета** — свет. Истребляет нежить, хранит реликвии и
     старые клятвы; его заклятый враг — Стража.

Вражда идёт по кольцу: 1↔2, 2↔3, 3↔4, 4↔1. Каждая сила ненавидит
следующую и ненавидима предыдущей. Союзы: Стража+Культ (1-3),
Гильдия+Орден (2-4) — противоположные стороны кольца.

Помощь одной злит её соперника (`RIVALS`), поэтому нельзя быть своим
для всех — в этом и смысл выбора. Репутация даёт скидки у торговцев,
меняет реплики жителей и влияет на частоту катаклизмов.
"""
from engine.models import Reply

# ключ -> (значок, имя, девиз, кого злит)
# Вражда идёт по кольцу: 1↔2, 2↔3, 3↔4, 4↔1.
# Стража ненавидит Гильдию, Гильдия — Культ, Культ — Орден,
# Орден — Стражу. Союзы: Стража+Культ (1-3), Гильдия+Орден (2-4).
FACTIONS = {
    "guard": ("🛡", "Стража Погоста",
              "Пока стоит частокол — стоит и деревня.", "scavengers"),
    "scavengers": ("💰", "Гильдия падальщиков",
                   "Мёртвым золото ни к чему.", "cult"),
    "cult": ("🌑", "Культ Пожирателя",
             "Всё кончится. Мы лишь торопим неизбежное.", "order"),
    "order": ("⚜️", "Орден Рассвета",
              "Свет не просит разрешения — он просто приходит.", "guard"),
}
ORDER = ["guard", "scavengers", "cult", "order"]
RIVALS = {k: v[3] for k, v in FACTIONS.items()}


def hostile(key_a, key_b) -> bool:
    """Враждуют ли две силы по кольцу вражды.

    Вражда идёт по краям кольца (1↔2, 2↔3, 3↔4, 4↔1) и обоюдна:
    Стража ненавидит Гильдию, а Гильдию ненавидит Стража. Диагональные
    союзы (Стража+Культ, Гильдия+Орден) враждой не считаются. Одна и та
    же сила или отсутствие фракции у кого-то из двоих — тоже не вражда.
    Используется, например, чтобы запретить пати между врагами.
    """
    if not key_a or not key_b or key_a == key_b:
        return False
    return RIVALS.get(key_a) == key_b or RIVALS.get(key_b) == key_a

# Ранги репутации: (порог, значок, звание)
RANKS = [
    (-100, "☠️", "Враг"),
    (-30, "😠", "Нежеланный"),
    (0, "😐", "Чужак"),
    (30, "🙂", "Знакомый"),
    (80, "🤝", "Союзник"),
    (150, "⭐", "Герой фракции"),
]
MIN_REP, MAX_REP = -200, 300
SPITE = 0.5                 # какая доля прироста уходит в минус сопернику

# За что дают репутацию: событие -> {фракция: сколько}. Отрицательные
# дельты — тематическая неприязнь (добавляется к SPITE-соперничеству).
# Союзники по кольцу: Стража+Культ (1-3), Гильдия+Орден (2-4).
DEEDS = {
    "undead_slain": {"guard": 2, "order": 2, "cult": 2, "scavengers": 2},  # все фракции одобряют защиту земель
    "beast_slain": {"guard": 1, "order": 1, "cult": 1, "scavengers": 1},               # убил зверя
    "grave_looted": {"scavengers": 4, "guard": -2, "order": -2},       # падальщики ценят, стража и орден — нет
    "chest_opened": {"scavengers": 1},               # вскрыл сундук
    "quest_done": {"guard": 3, "order": 2},          # выполнил задание жителя
    "boss_slain": {"guard": 5, "order": 3, "cult": 3},
    "cataclysm_survived": {"cult": 4},               # пережил бедствие
    "landmark_found": {"cult": 2},                   # тронул древнее
}

# Нежить и звери — по названию твари, чтобы не заводить новое поле.
UNDEAD = ("зомби", "скелет", "призрак", "костя", "могильн", "плакальщ",
          "голем из костей", "жрец")

SHOP_DISCOUNT = 0.25        # максимальная скидка у своей фракции
DISCOUNT_FROM = 30          # скидка начинается со звания «Знакомый»
CULT_CATACLYSM = 1.6        # во столько раз культист ускоряет беды
GUARD_CATACLYSM = 0.6       # и во столько замедляет страж


# ── хранилище ───────────────────────────────────────────────

def all_of(p):
    """Репутация игрока по всем фракциям."""
    rep = getattr(p, "reputation", None)
    if not isinstance(rep, dict):
        rep = {}
        p.reputation = rep
    for key in FACTIONS:
        rep.setdefault(key, 0)
    return rep


def value(p, key):
    return int(all_of(p).get(key, 0))


def rank(points):
    """Значок и звание по числу очков."""
    icon, title = RANKS[0][1], RANKS[0][2]
    for threshold, ic, ti in RANKS:
        if points >= threshold:
            icon, title = ic, ti
    return icon, title


def standing(p, key):
    return rank(value(p, key))


def allegiance(p):
    """Фракция, к которой игрок ближе всего, или None если ни к кому."""
    rep = all_of(p)
    best = max(rep, key=lambda k: rep[k])
    return best if rep[best] >= 30 else None


# ── начисление ──────────────────────────────────────────────

def award(store, p, deed, scale=1):
    """Записать поступок. Возвращает строки-уведомления для экрана.

    Прирост у одной фракции автоматически злит её соперника: репутация —
    это выбор стороны, а не копилка, которую можно наполнить везде.
    """
    table = DEEDS.get(deed)
    if not table:
        return []
    rep = all_of(p)
    moved = {}
    for key, delta in table.items():
        step = int(delta * scale)
        if not step:
            continue
        moved[key] = moved.get(key, 0) + step
        if step > 0:                              # соперник недоволен
            foe = RIVALS.get(key)
            if foe:
                moved[foe] = moved.get(foe, 0) - max(1, int(step * SPITE))

    lines = []
    for key, step in moved.items():
        before = rep.get(key, 0)
        rep[key] = max(MIN_REP, min(MAX_REP, before + step))
        if rep[key] == before:
            continue
        icon = FACTIONS[key][0]
        sign = "+" if step > 0 else ""
        was_icon, was_title = rank(before)
        now_icon, now_title = rank(rep[key])
        note = f"{icon} {FACTIONS[key][1]}: {sign}{step}"
        if now_title != was_title:                # ранг сменился — это событие
            note += f" → {now_icon} <b>{now_title}</b>"
        lines.append(note)
    if lines and store is not None:
        store.save_player(p)
    return lines


def on_kill(store, p, mob_index):
    """Репутация за убитую тварь: нежить ценят одни, зверьё — другие."""
    from engine import data

    try:
        name = data.MOBS[int(mob_index)][0].lower()
    except (IndexError, ValueError, TypeError):
        return []
    deed = "undead_slain" if any(w in name for w in UNDEAD) else "beast_slain"
    return award(store, p, deed)


# ── что даёт репутация ──────────────────────────────────────

def discount(p):
    """Скидка в лавке от лучшей фракции: 0..SHOP_DISCOUNT.

    Начинается не с первого очка, а со звания «Знакомый»: иначе одна
    убитая крыса уже меняла бы ценники, и скидка ничего не значила бы.
    """
    best = max(value(p, k) for k in FACTIONS)
    if best < DISCOUNT_FROM:
        return 0.0
    span = MAX_REP - DISCOUNT_FROM
    grown = (best - DISCOUNT_FROM) / span if span > 0 else 1.0
    return round(min(SHOP_DISCOUNT, SHOP_DISCOUNT * grown), 3)


def price_mult(p):
    """Множитель цены покупки с учётом репутации."""
    return 1.0 - discount(p)


def cataclysm_mult(store, p=None):
    """Как настроения игроков влияют на частоту бедствий.

    Культисты торопят конец света, стража его отдаляет. Считаем по всем
    героям сразу: это общий мир, а не личная погода.
    """
    if store is None:
        return 1.0
    cult = guard = 0
    for q in store.players.values():
        if not getattr(q, "created_char", False):
            continue
        cult += max(0, value(q, "cult"))
        guard += max(0, value(q, "guard"))
    if not cult and not guard:
        return 1.0
    if cult > guard * 1.5:
        return CULT_CATACLYSM
    if guard > cult * 1.5:
        return GUARD_CATACLYSM
    return 1.0


def greeting(p, npc_index):
    """Как житель здоровается с игроком — по его репутации.

    NPC приписаны фракциям по роду занятий: стража доверяет тем, кто
    защищает деревню, скупщик — тем, кто носит добычу.
    """
    from engine import data

    key = npc_faction(npc_index)
    if key is None:
        return ""
    points = value(p, key)
    icon, title = rank(points)
    if points >= 80:
        mood = "Тебе здесь рады."
    elif points >= 30:
        mood = "Тебя узнают."
    elif points <= -30:
        mood = "На тебя смотрят косо."
    elif points <= -100:
        mood = "Тебе здесь не рады."
    else:
        mood = "Тебя не знают."
    return f"\n\n{FACTIONS[key][0]} <i>{FACTIONS[key][1]}: {icon} {title}. {mood}</i>"


def npc_faction(npc_index):
    """К какой силе принадлежит житель."""
    from engine import data

    try:
        kind = data.NPCS[int(npc_index)][2]
        name = data.NPCS[int(npc_index)][0]
    except (IndexError, ValueError, TypeError):
        return None
    if "Паладин" in name or "Рыцарь" in name or "Капеллан" in name:
        return "order"
    if "Скупщик" in name or "Наёмник" in name:
        return "scavengers"
    if "Гробовщик" in name or "Летописец" in name:
        return "cult"
    if kind in ("healer", "smith", "storyteller"):
        return "guard"
    return "guard"


def refuses(p, npc_index):
    """Откажется ли житель иметь дело: враждебность имеет цену."""
    key = npc_faction(npc_index)
    return key is not None and value(p, key) <= -100


# ── экран ───────────────────────────────────────────────────

def card(store, p):
    """Экран репутации: кто как относится и что это даёт."""
    rep = all_of(p)
    lines = ["🧭 <b>Репутация</b>", ""]
    for key in ORDER:
        icon, name, motto, foe = FACTIONS[key]
        points = rep.get(key, 0)
        r_icon, r_title = rank(points)
        bar = _bar(points)
        lines.append(f"{icon} <b>{name}</b> — {r_icon} {r_title} ({points})")
        lines.append(bar)
        lines.append(f"<i>{motto}</i>")
        lines.append("")

    side = allegiance(p)
    if side:
        lines.append(f"⚔️ Твоя сторона: {FACTIONS[side][0]} <b>{FACTIONS[side][1]}</b>")
        lines.append(f"<i>Соперник — {FACTIONS[RIVALS[side]][1]}.</i>")
    else:
        lines.append("<i>Ты пока никому не свой. Помогай — и тебя заметят.</i>")

    disc = discount(p)
    if disc:
        lines.append(f"💵 Скидка в лавке: <b>{int(disc * 100)}%</b>")
    lines.append("\n<i>Помощь одной силе злит противоположную — выбирай.</i>")
    return Reply(text="\n".join(lines), keyboard=[[("◀️ Меню", "menu")]])


def _bar(points, size=10):
    """Полоска от вражды к союзу."""
    span = MAX_REP - MIN_REP
    filled = int((points - MIN_REP) / span * size)
    filled = max(0, min(size, filled))
    return "🟥" * 0 + "🟩" * filled + "⬛" * (size - filled)
