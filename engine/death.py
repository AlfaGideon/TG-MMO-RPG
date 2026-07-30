"""Цена смерти: надгробие с добром и раны после воскрешения.

Раньше поражение стоило 20% золота и телепорта на спавн — неудобство, не
более. Риск ничем не отличался от осторожности.

Теперь смерть оставляет след в мире:

  🪦 **Надгробие** — потерянное золото не исчезает, а лежит на месте гибели.
     Дошёл обратно — забрал всё; погиб по дороге — потерял окончательно.
     Обычная вылазка превращается в напряжённую, без единой новой механики.
  🩸 **Раны** — временный штраф к статам, который лечится у Лекаря или
     проходит сам. У лекаря наконец появляется работа.

Надгробия живут в настройках (общие для бота и панели), раны — у игрока.
"""
import time

from engine import data, rules
from engine.models import Reply

GRAVES = "graves"           # список надгробий в settings
WOUND_MINUTES = 10          # сколько держится ранение
WOUND_PENALTY = 0.10        # −10% к статам, пока не залечено
GRAVE_HOURS = 24            # через сутки бесхозное надгробие истлевает
MAX_GRAVES = 200


# ── надгробия ───────────────────────────────────────────────

def _graves(store):
    lst = store.settings.get(GRAVES)
    if not isinstance(lst, list):
        lst = []
        store.settings[GRAVES] = lst
    return lst


def bury(store, p, gold, items_lost=()):
    """Оставить надгробие с добром на месте гибели. Возвращает запись.

    `items_lost` — индексы вещей, выпавших из сумки: они ждут хозяина
    вместе с золотом. Вещи из защищённого кармана сюда не попадают.
    """
    items_lost = list(items_lost or [])
    if gold <= 0 and not items_lost:
        return None
    grave = {"owner": int(p.tg_id), "name": p.name, "gold": int(gold),
             "items": items_lost,
             "loc": int(p.loc), "x": int(p.x), "y": int(p.y),
             "at": int(time.time())}
    lst = _graves(store)
    # Одна могила на героя: старая рассыпается, чтобы не копить золото полем.
    lst[:] = [g for g in lst if int(g.get("owner", 0)) != int(p.tg_id)]
    lst.append(grave)
    store.settings[GRAVES] = lst[-MAX_GRAVES:]
    return grave


def at(store, loc, x, y):
    """Надгробие в этой клетке или None."""
    decay(store)
    for g in _graves(store):
        if (int(g["loc"]), int(g["x"]), int(g["y"])) == (int(loc), int(x), int(y)):
            return g
    return None


def mine(store, p):
    """Где лежит собственное надгробие игрока (или None)."""
    for g in _graves(store):
        if int(g.get("owner", 0)) == int(p.tg_id):
            return g
    return None


def keys(store):
    """Ключи клеток с надгробиями — для карты."""
    return {f"{g['loc']}:{g['x']}:{g['y']}" for g in _graves(store)}


def claim(store, p):
    """Забрать содержимое надгробия под ногами."""
    g = at(store, p.loc, p.x, p.y)
    if g is None:
        return Reply(alert="Здесь нечего забирать.")
    own = int(g.get("owner", 0)) == int(p.tg_id)
    gold = int(g.get("gold", 0))
    goods = list(g.get("items") or [])
    # Чужое добро тоже можно взять — но половина рассыпается прахом.
    taken = gold if own else gold // 2
    if not own and goods:
        goods = goods[:max(0, len(goods) // 2)]
    p.gold += taken
    p.inventory.extend(goods)
    _graves(store)[:] = [x for x in _graves(store) if x is not g]
    store.save_player(p)

    from engine import factions
    rep_lines = [] if own else factions.award(store, p, "grave_looted")

    got = [f"+{taken} 🪙"] if taken else []
    if goods:
        names = ", ".join(rules.item(i)["name"] for i in goods[:4])
        more = f" и ещё {len(goods) - 4}" if len(goods) > 4 else ""
        got.append(f"🎒 вещей: {len(goods)} — {names}{more}")
    body = "\n".join(got) if got else "здесь уже пусто"
    if own:
        text = (f"🪦 <b>Ты вернулся за своим.</b>\n\n{body}\n\n"
                f"<i>Земля отпускает то, что взяла.</i>")
    else:
        rep = ("\n\n" + "\n".join(rep_lines)) if rep_lines else ""
        text = (f"🪦 <b>Чужая могила</b>\n\n{g.get('name', 'Некто')} больше не "
                f"придёт за этим.\nТы забрал: {body}\n\n"
                f"<i>Половина рассыпалась прахом — мародёрство не в чести.</i>"
                f"{rep}")
    return Reply(text=text, keyboard=[[("◀️ В мир", "world")]])


def decay(store):
    """Убрать истлевшие надгробия. Возвращает, сколько снято."""
    lst = _graves(store)
    limit = time.time() - GRAVE_HOURS * 3600
    old = [g for g in lst if float(g.get("at", 0)) < limit]
    if old:
        lst[:] = [g for g in lst if g not in old]
    return len(old)


# ── раны ────────────────────────────────────────────────────

def wound(p, minutes=WOUND_MINUTES):
    """Пометить героя раненым на N минут."""
    p.wounded_until = time.time() + minutes * 60


def wounded(p):
    return time.time() < float(getattr(p, "wounded_until", 0) or 0)


def wound_left(p):
    """Сколько минут ещё болеть (0 — здоров)."""
    left = float(getattr(p, "wounded_until", 0) or 0) - time.time()
    return max(0, int(left // 60) + (1 if left > 0 else 0))


def heal_wounds(p):
    p.wounded_until = 0


def penalty(p):
    """Множитель статов: раненый слабее. 1.0 — здоров."""
    return 1.0 - WOUND_PENALTY if wounded(p) else 1.0


def note(p):
    """Строка о ранении для экранов (пустая, если здоров)."""
    if not wounded(p):
        return ""
    return (f"🩸 <i>Раны кровоточат: −{int(WOUND_PENALTY * 100)}% к статам, "
            f"ещё ~{wound_left(p)} мин. Лекарь в Погосте поможет.</i>")


# ── экран гибели ────────────────────────────────────────────

def defeat(store, p, mob_name):
    """Поражение: надгробие, раны, возврат на спавн."""
    from engine import world as W

    from engine import stash

    lost = p.gold // 5
    p.gold -= lost
    dropped = stash.drop_on_death(p, store=store)   # часть сумки выпадает
    kept = len(getattr(p, "stash", None) or [])
    grave = bury(store, p, lost, dropped) if store is not None else None
    where = (data.LOCATIONS[p.loc][0] if p.loc < len(data.LOCATIONS) else "?")
    spot = f"{where} [{p.x},{p.y}]"

    from engine import dungeon
    was_deep = dungeon.inside(p)
    dungeon.bail_out(store, p)            # из подземелья выносит наружу
    wound(p)
    p.hp = max(1, rules.stats(p)["max_hp"] // 4)
    p.loc, p.x, p.y = 0, W.SPAWN[0], W.SPAWN[1]
    p.combat = {}

    lines = [f"💀 <b>Поражение...</b>\n\n{mob_name} оказался сильнее. "
             f"Ты очнулся в Погосте Костров."]
    if grave:
        lines.append(f"\n🪦 Осталось там, где ты пал: <b>{lost}</b> 🪙"
                     f"\n📍 {spot}")
        note_items = stash.death_note(dropped, kept)
        if note_items:
            lines.append(note_items)
        lines.append("<i>Вернись и забери — если успеешь за сутки.</i>")
    elif kept:
        lines.append(f"\n🔒 В защищённом кармане уцелело: <b>{kept}</b>")
    if was_deep:
        lines.append("\n🕳 <i>Подземелье выплюнуло тебя наружу.</i>")
    lines.append(f"\n{note(p)}")

    rows = [[("🧭 В мир", "world")]]
    if grave:
        rows.insert(0, [("🪦 Где моя могила?", "grave")])
    rows.append([("◀️ Меню", "menu")])
    if store is not None:
        store.save()
    return Reply(text="\n".join(lines), keyboard=rows)


def grave_card(store, p):
    """Подсказка, куда идти за своим золотом."""
    g = mine(store, p)
    if g is None:
        return Reply(alert="Твоих могил в мире нет.")
    where = (data.LOCATIONS[g["loc"]][0]
             if g["loc"] < len(data.LOCATIONS) else "?")
    same = (int(g["loc"]), int(g["x"]), int(g["y"])) == (p.loc, p.x, p.y)
    left = GRAVE_HOURS - int((time.time() - float(g.get("at", 0))) // 3600)
    rows = [[("💰 Забрать", "claim")]] if same else []
    rows.append([("◀️ В мир", "world")])
    body = ("Ты стоишь на ней — забирай." if same
            else "Дойди до этого места, чтобы вернуть своё.")
    goods = list(g.get("items") or [])
    goods_line = f"\n🎒 Вещей: {len(goods)}" if goods else ""
    return Reply(text=(f"🪦 <b>Твоя могила</b>\n\n💰 {g['gold']} 🪙{goods_line}\n"
                       f"📍 {where} [{g['x']},{g['y']}]\n"
                       f"⌛ Истлеет через ~{max(0, left)} ч\n\n{body}"),
                 keyboard=rows)
