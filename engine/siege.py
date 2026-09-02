"""Осады угловых замков: общие правила для обоих стеков (IDEAS-next, пункт 4).

На сервере осада живёт строкой `WorldEvent(kind="siege")` в БД, в браузерном
стеке — списком в `store.settings["sieges"]`. Числа и правила исхода живут
здесь — это единственный источник для обоих стеков (тот же узор, что у
катаклизмов и знамений: правила в `engine/`, хранилище разное).

Правила простые, почти жестокие:

* осаждают — только свои: герой, чья преданность (`factions.allegiance`,
  та же функция в обоих стеках) совпала с атакующей фракцией, бьёт по
  воротам;
* остальные — на стене: чинят ворота. Замок кому-то дом, и защищать его
  приходят соседи, а не только гарнизон;
* удар раз в минуту на героя (в браузере — по имени в store, на сервере —
  по id персонажа в памяти процесса: то же состояние, что у вызовов дуэли);
* hp ворот упал до нуля — падение: осада заканчивается, добивший получает
  золото и репутацию своей стороны;
* истёк срок — осада снята: стену удержали, события не было.

Репутация за ОСАДУ начисляется прямой корректировкой своей стороны
(`bump_side`), а не через DEEDS: поступок не статичен — он зависит от того,
на чьей стене ты стоял. SPITE-вражде тут не при чём: ворота не крадут
расположение соседей, их держат.
"""
import random
import time

RULES = {
    "hp": 3000,               # прочность ворот
    "hours": 4.0,             # сколько длится осада
    "cooldown": 60,           # секунд между ударами одного героя
    "assault_base": 120,      # урон по воротам: база
    "assault_per_level": 8,   #   + за уровень
    "repair_base": 90,        # починка: заведомо медленнее удара — иначе
    "repair_per_level": 4,    #   стена была бы вечной
    "gold_assault": 25,       # бронза за удар по воротам
    "gold_defend": 10,        # бронза за починку
    "gold_capture": 400,      # единая награда за падение (добившему)
    "rep_hit": 1,             # репутация своей стороне за любое действие
    "rep_capture": 6,         #   и щедрая — за падение/удержание
}

# Кто держит угловые замки — совпадает с `data.LOCATIONS` и мирогенерацией
# (core/worldgen.py, engine/world.py: «Замок …» по углам карты 10×10).
CASTLE_OWNERS = {
    "Замок Рассвета": "order",        # белые башни Ордена
    "Замок Теней": "cult",            # чёрные шпили Культа
    "Замок Глубин": "scavengers",     # падальщики коптят глубины
    "Замок Пепла": "guard",           # сожжённые, но наши
}
DEFAULT_GARRISON = "guard"            # незнакомая крепость — под Стражей


# ── чистые правила (общие для обоих стеков) ────────────────

def attacker_of(siege) -> str:
    """Фракция-осаждающая. На сервере это `WorldEvent.key` = «siege_<key>»."""
    key = str(siege.get("attacker") if isinstance(siege, dict)
              else getattr(siege, "key", "") or "")
    return key[6:] if key.startswith("siege_") else key


def defender_faction(location_name: str) -> str:
    name = str(location_name or "")
    for castle, faction in CASTLE_OWNERS.items():
        if castle in name:
            return faction
    return DEFAULT_GARRISON


def role_for(allegiance, attacker: str) -> str:
    """«assault» у своей фракции на штурме, «defend» у всех остальных."""
    return "assault" if allegiance and allegiance == attacker else "defend"


def strike_roll(role: str, level: int, rng=None) -> int:
    """Что вышло из руки: база + рост по уровню, разброс ±20 %."""
    rng = rng or random
    if role == "assault":
        base = RULES["assault_base"] + RULES["assault_per_level"] * max(1, int(level))
    else:
        base = RULES["repair_base"] + RULES["repair_per_level"] * max(1, int(level))
    return max(1, int(base * rng.uniform(0.8, 1.2)))


def apply_roll(hp: int, max_hp: int, role: str, roll: int) -> tuple[int, str]:
    """Применить удар к прочности ворот. Возвращает (новый hp, исход).

    Исходы: «progress» — идёт, «captured» — ворота пали. Починка не
    поднимает стену выше максимума и не воскрешает уже взятый замок.
    """
    hp = int(hp)
    if role == "assault":
        hp = hp - int(roll)
        if hp <= 0:
            return 0, "captured"
        return hp, "progress"
    return min(int(max_hp), hp + int(roll)), "progress"


def bump_side(rep: dict, faction: str, delta: int, min_rep=-200, max_rep=300) -> int:
    """Прямая правка репутации одной стороны. Возвращает новое значение."""
    if not faction or not delta:
        return int((rep or {}).get(faction, 0))
    before = int(rep.get(faction, 0) or 0)
    rep[faction] = max(min_rep, min(max_rep, before + int(delta)))
    return rep[faction]


def gold_for(role: str, captured: bool) -> int:
    if captured and role == "assault":
        return int(RULES["gold_capture"])
    return int(RULES["gold_assault"] if role == "assault" else RULES["gold_defend"])


def left_minutes(until_ts: float, now=None) -> int:
    return max(0, int(int(until_ts) - int(now or time.time())) // 60)


# ── браузерное хранилище (store.settings) ──────────────────

EVENTS = "sieges"
CD = "siege_cd"           # {имя героя: unix-секунда последнего удара}
_seq = [0]


def _events(store):
    lst = store.settings.get(EVENTS)
    if not isinstance(lst, list):
        lst = []
        store.settings[EVENTS] = lst
    return lst


def tick(store, now=None):
    """Снять осады, у которых вышел срок. Возвращает список снятых."""
    now = time.time() if now is None else now
    live = _events(store)
    kept, done = [], []
    for s in live:
        if float(s.get("until", 0)) <= now:
            done.append(s)
        else:
            kept.append(s)
    if len(kept) != len(live):
        store.settings[EVENTS] = kept
        store.save()
    return done


def active(store, loc=None, now=None):
    tick(store, now)
    out = _events(store)
    if loc is None:
        return list(out)
    return [s for s in out if int(s["loc"]) == int(loc)]


def start(store, attacker: str, loc: int, hp=None, hours=None, now=None):
    """Начать осаду замка фракцией `attacker` (loc — индекс data.LOCATIONS)."""
    from engine import data
    from engine import factions
    if attacker not in factions.FACTIONS:
        raise ValueError("Неизвестная фракция")
    if not 0 <= int(loc) < len(data.LOCATIONS):
        raise ValueError("Нет такой локации")
    if active(store, loc):
        raise ValueError("Этот замок уже осаждают")
    now = time.time() if now is None else now
    ev = {
        "id": _next_id(store),
        "loc": int(loc),
        "attacker": attacker,
        "hp": int(hp if hp is not None else RULES["hp"]),
        "max_hp": int(hp if hp is not None else RULES["hp"]),
        "started": int(now),
        "until": int(now + float(hours if hours is not None else RULES["hours"]) * 3600),
    }
    _events(store).append(ev)
    store.save()
    return ev


def _next_id(store):
    """Идентификатор осады: максимум существующего + 1 (после снятия
    хвост списка не переиспользует id — cooldown-записи на это не влияют,
    но летопись/лог читаются чище)."""
    live = _events(store)
    return 1 + max((int(s.get("id", 0)) for s in live), default=0)


def cooldown_left(store, p, now=None) -> int:
    now = time.time() if now is None else now
    cd = store.settings.get(CD)
    if not isinstance(cd, dict):
        cd = {}
        store.settings[CD] = cd
    return max(0, int(RULES["cooldown"] - (now - float(cd.get(getattr(p, "name", "?"), 0) or 0))))


def hit(store, p, rng=None, now=None) -> dict:
    """Один ход героя: штурм или починка — роль определяется преданностью.

    Возвращает {"ok": bool, "reason"|"role"|"roll"|"outcome"|"gold"|"text"}.
    """
    from engine import currency, factions
    now = time.time() if now is None else now
    live = active(store, p.loc, now)
    if not live:
        return {"ok": False, "reason": "Здесь нет осады."}
    if cooldown_left(store, p, now) > 0:
        return {"ok": False,
                "reason": f"Ты только что бил. Отдышись {cooldown_left(store, p, now)} с."}
    siege = live[0]
    attacker = attacker_of(siege)
    role = role_for(factions.allegiance(p), attacker)
    roll = strike_roll(role, p.level, rng)
    hp, outcome = apply_roll(int(siege["hp"]), int(siege["max_hp"]), role, roll)
    siege["hp"] = hp
    if outcome == "captured":
        _events(store).remove(siege)
    cd = store.settings.setdefault(CD, {})
    cd[getattr(p, "name", "?")] = now
    store.save()

    side = attacker if role == "assault" else defender_faction(_loc_name(p.loc))
    rep = factions.all_of(p)
    bump = RULES["rep_hit"] + (RULES["rep_capture"] if outcome == "captured" else 0)
    bump_side(rep, side, bump)
    gold = gold_for(role, outcome == "captured")
    if gold:
        currency.add_currency(p, bronze=gold)
    store.save()
    return {"ok": True, "role": role, "roll": roll, "outcome": outcome,
            "hp": hp, "gold": gold, "rep": bump, "side": side}


def _loc_name(loc):
    from engine import data
    try:
        return str(data.LOCATIONS[int(loc)][0])
    except (ValueError, TypeError, IndexError):
        return ""


# ── автогенерация и экраны браузера ─────────────────────────

COUNTER = "siege_n"


def _rng(store):
    """Случайность войн: свой сид + счётчик — как у бедствий, мир
    воспроизводим по одному числу (SEEDS в engine/world.py)."""
    from engine import world as W
    seeds = W.seeds_of(store.settings)
    n = int(store.settings.get(COUNTER, 0)) + 1
    store.settings[COUNTER] = n
    return random.Random(seeds["siege"] * 1_000_003 + n * 7919)


def auto(store, rng=None, now=None) -> dict | None:
    """Мир сам воюет: двигаясь, игрок иногда натыкается на зарождающуюся
    осаду в одном из угловых замков."""
    now = time.time() if now is None else now
    rng = rng or _rng(store)
    if not store.settings.get("siege_auto", True):
        return None
    if len(active(store, None, now)) >= 1:      # одна война — уже громко
        return None
    if rng.random() >= float(store.settings.get("siege_chance", 0.012) or 0):
        return None
    castles = castles_idx()
    if not castles:
        return None
    from engine import factions
    attacker = rng.choice(list(factions.FACTIONS))
    loc = rng.choice(castles)
    owner = defender_faction(_loc_name(loc))
    if owner == attacker:
        return None                  # на себя не воюют
    try:
        return start(store, attacker, loc, now=now)
    except ValueError:
        return None


def castles_idx() -> list:
    """Индексы угловых замков в data.LOCATIONS."""
    return [i for i, name in enumerate(_loc_names())
            if name and "Замок" in name]


def _loc_names():
    from engine import data
    return [row[0] for row in data.LOCATIONS]


def banner(store, loc, now=None) -> str:
    """Строка для экрана клетки (пустая, если тихо)."""
    live = active(store, loc, now)
    if not live:
        return ""
    from engine import factions
    s = live[0]
    atk = factions.FACTIONS.get(attacker_of(s), ("⚔️", attacker_of(s)))
    return (f"🔥 {atk[0]} {atk[1]} осаждают замок · "
            f"ворота {s['hp']}/{s['max_hp']} · ещё {left_minutes(s['until'], now)} мин")


def screen(store, p, now=None):
    """Экран осады: что происходит и что может сделать герой."""
    from engine import factions
    from engine.models import Reply
    now = time.time() if now is None else now
    live = active(store, p.loc, now)
    if not live:
        return Reply(text="🔕 <b>Осада ушла</b>\n\n<i>Стена устояла, война "
                          "разошлась по кустам.</i>",
                     keyboard=[[(("🧭 В мир", "world"),)][0]] if False else
                     [[("🧭 В мир", "world")]])
    s = live[0]
    attacker = attacker_of(s)
    role = role_for(factions.allegiance(p), attacker)
    atk = factions.FACTIONS.get(attacker, ("⚔️", attacker))
    side_name = atk[1] if role == "assault" else "защитники замка"
    left = left_minutes(s["until"], now)
    cool = cooldown_left(store, p, now)
    text = (
        "🔥 <b>Осада замка!</b>\n\n"
        f"{atk[0]} <b>{atk[1]}</b> бьёт по главным воротам.\n"
        f"Прочность ворот: <b>{s['hp']}/{s['max_hp']}</b>\n"
        f"До отступления: <b>{left} мин</b>\n\n"
        f"<i>Твоя сторона в этом бою: <b>{side_name}</b>.</i>"
    )
    rows = []
    if cool:
        rows.append([(f"⏳ Отдышись: {cool} с", "siege")])
    else:
        rows.append([("⚔️ Бить по воротам" if role == "assault" else "🛡 Чинить ворота",
                      "siege:hit")])
    rows.append([("🧭 В мир", "world")])
    return Reply(text=text, keyboard=rows)


def button(store, p, rows):
    """Строка для экрана клетки: вход в осаду, только если она под ногами.

    Здесь же `auto()` — мир воюет на каждом взгляде на клетку. Один вызов
    вместо четырёх в game.py: модуль роутера держится в лимите 500 строк
    (tests/test_wiring.py), а вставка кнопки и зачаться войны — забота
    осады. Ролл auto завязан на собственный сид-счётчик, поэтому повторный
    взгляд на клетку ничего не «подкручивает» — последовательность та же.
    """
    auto(store)
    if active(store, p.loc):
        rows.insert(0, [("🔥 Осада замка!", "siege")])


def play(store, p, arg=""):
    """Маршрут do_siege: экран или один ход (siege:hit)."""
    from engine.models import Reply
    if arg == "hit":
        res = hit(store, p)
        if not res.get("ok"):
            r = screen(store, p)
            r.alert = res.get("reason", "Не вышло.")
            return r
        r = screen(store, p)
        head = ("💥 Удар по воротам нанёс " if res["role"] == "assault"
                else "🛡 Ворота укреплены на ")
        bits = [f"{head}{res['roll']}", f"🪙 +{res['gold']}🟤",
                f"⭐ репутация +{res['rep']}"]
        if res["outcome"] == "captured":
            bits.append("⚡ Замок пал!")
        r.alert = " · ".join(bits)
        return r
    if arg in ("", None):
        return screen(store, p)
    return Reply(alert="Неизвестное действие осады.")
