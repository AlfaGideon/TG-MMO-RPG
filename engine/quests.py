"""Задания: цель для игрока и повод вернуться завтра.

Три вида, и все проверяются по тому, что в игре уже считается:
  hunt    — убить тварей вида (счётчик ведём при победе в бою);
  reach   — дойти до локации (сверяем с `p.visited`, туман войны уже есть);
  deliver — принести предмет заказчику (смотрим в сумке).

Состояние живёт в `p.quests`: {id задания: {"n": прогресс, "done": сдано}}.
Ежедневные сбрасываются раз в сутки по `p.quest_day`.
"""
import time

from engine import data, factions, items, money, rules
from engine.models import Reply

HUNT, REACH, DELIVER = "hunt", "reach", "deliver"
DAILY_LIMIT = 2                 # сколько ежедневных доступно за раз


def _row(qid):
    for q in data.QUESTS:
        if q[0] == int(qid):
            return q
    return None


def fields(q):
    """Кортеж задания -> словарь, чтобы не помнить порядок полей."""
    return dict(id=q[0], name=q[1], text=q[2], npc=q[3], kind=q[4],
                target=q[5], need=q[6], gold=q[7], exp=q[8], item=q[9],
                level=q[10], daily=q[11])


def state(p):
    st = getattr(p, "quests", None)
    if not isinstance(st, dict):
        st = {}
        p.quests = st
    return st


# ── ежедневный сброс ────────────────────────────────────────

def _today():
    return time.strftime("%Y-%m-%d")


def refresh_daily(p):
    """Раз в сутки снимает отметки с ежедневных заданий. True, если сбросили."""
    if getattr(p, "quest_day", "") == _today():
        return False
    st = state(p)
    for q in data.QUESTS:
        if q[11]:
            st.pop(str(q[0]), None)
    p.quest_day = _today()
    return True


# ── доступность ─────────────────────────────────────────────

def taken(p, qid):
    return str(qid) in state(p)


def done(p, qid):
    return bool(state(p).get(str(qid), {}).get("done"))


def available(p, npc_index=None):
    """Задания, которые игрок может взять у этого NPC (или вообще)."""
    refresh_daily(p)
    out = []
    dailies = 0
    for q in data.QUESTS:
        f = fields(q)
        if npc_index is not None and f["npc"] != int(npc_index):
            continue
        if p.level < f["level"] or taken(p, f["id"]):
            continue
        if f["daily"]:
            dailies += 1
            if dailies > DAILY_LIMIT:
                continue
        out.append(q)
    return out


def active(p):
    """Взятые и ещё не сданные."""
    refresh_daily(p)
    st = state(p)
    return [q for q in data.QUESTS
            if str(q[0]) in st and not st[str(q[0])].get("done")]


def take(p, qid):
    q = _row(qid)
    if q is None:
        return Reply(alert="Такого задания нет.")
    f = fields(q)
    if p.level < f["level"]:
        return Reply(alert=f"Нужен {f['level']} уровень.")
    if taken(p, qid):
        return Reply(alert="Это задание уже у тебя.")
    state(p)[str(qid)] = {"n": 0, "done": False}
    if f["kind"] == REACH and _reached(p, f["target"]):
        state(p)[str(qid)]["n"] = f["need"]      # уже бывал там
    return Reply(text=f"📜 <b>Задание принято</b>\n\n<b>{f['name']}</b>\n"
                      f"<i>{f['text']}</i>\n\n{goal_line(p, q)}",
                 keyboard=[[("📜 Мои задания", "quests")], [("◀️ В мир", "world")]])


def abandon(p, qid):
    if not taken(p, qid):
        return Reply(alert="Ты за это не брался.")
    state(p).pop(str(qid), None)
    return Reply(text="🚮 Задание отброшено.", keyboard=[[("📜 Задания", "quests")]])


# ── прогресс ────────────────────────────────────────────────

def _reached(p, loc):
    return any(k.startswith(f"{int(loc)}:") for k in (getattr(p, "visited", []) or []))


def on_kill(p, mob_index):
    """Победа над тварью двигает охотничьи задания. Возвращает готовые."""
    ready = []
    for q in active(p):
        f = fields(q)
        if f["kind"] != HUNT:
            continue
        if f["target"] not in (-1, int(mob_index)):
            continue
        rec = state(p)[str(f["id"])]
        rec["n"] = min(f["need"], rec.get("n", 0) + 1)
        if rec["n"] >= f["need"]:
            ready.append(q)
    return ready


def on_enter(p, loc):
    """Приход в локацию закрывает разведку."""
    ready = []
    for q in active(p):
        f = fields(q)
        if f["kind"] == REACH and int(f["target"]) == int(loc):
            rec = state(p)[str(f["id"])]
            rec["n"] = f["need"]
            ready.append(q)
    return ready


def progress(p, q):
    """Сколько сделано из нужного."""
    f = fields(q)
    if f["kind"] == DELIVER:
        have = sum(1 for i in p.inventory if int(i) == int(f["target"]))
        return min(have, f["need"]), f["need"]
    rec = state(p).get(str(f["id"]), {})
    return min(rec.get("n", 0), f["need"]), f["need"]


def complete(p, q):
    n, need = progress(p, q)
    return n >= need


def goal_line(p, q):
    """Человеческая строка цели с прогрессом."""
    f = fields(q)
    n, need = progress(p, q)
    if f["kind"] == HUNT:
        who = data.MOBS[f["target"]][0] if f["target"] >= 0 else "любые твари"
        what = f"⚔️ {who}: {n}/{need}"
    elif f["kind"] == REACH:
        where = (data.LOCATIONS[f["target"]][0]
                 if f["target"] < len(data.LOCATIONS) else "?")
        what = f"🧭 Дойти: {where} — {'да' if n >= need else 'ещё нет'}"
    else:
        it = rules.item(f["target"])
        what = f"🎒 {it['icon']} {it['name']}: {n}/{need}"
    prize = f"{money.fmt(f['gold'])} · ⭐ {f['exp']}"
    if f["item"] >= 0:
        it = rules.item(f["item"])
        prize += f" · {it['icon']} {it['name']}"
    return f"{what}\n🎁 Награда: {prize}"


# ── сдача ───────────────────────────────────────────────────

def hand_in(store, p, qid):
    q = _row(qid)
    if q is None or not taken(p, qid):
        return Reply(alert="Это задание не у тебя.")
    if done(p, qid):
        return Reply(alert="Уже сдано.")
    f = fields(q)
    if not complete(p, q):
        return Reply(alert="Задание ещё не выполнено.")

    if f["kind"] == DELIVER:                 # предмет уходит заказчику
        for _ in range(f["need"]):
            if int(f["target"]) in p.inventory:
                p.inventory.remove(int(f["target"]))

    money.earn(p, f["gold"])
    levels = rules.add_exp(p, f["exp"])
    lines = [f"✅ <b>{f['name']}</b> — выполнено!",
             f"💰 {money.plus(f['gold'])}   ⭐ +{f['exp']}"]
    if f["item"] >= 0:
        p.inventory.append(int(f["item"]))
        inst = items.create(store, int(f["item"]), source="quest",
                            owner=p.tg_id, luck=p.luck, detail=f["name"])
        if inst is not None:
            lines.append(f"📜 Награда: {inst['icon']} <b>{items.title(inst)}</b>")
        else:
            it = rules.item(f["item"])
            lines.append(f"📜 Награда: {it['icon']} {it['name']}")
    lines.extend(factions.award(store, p, "quest_done"))
    if levels:
        lines.append(f"\n🎖 <b>Новый уровень: {p.level}!</b>")

    if f["daily"]:
        state(p).pop(str(qid), None)         # завтра можно взять снова
    else:
        state(p)[str(qid)]["done"] = True
    store.save_player(p)
    return Reply(text="\n".join(lines),
                 keyboard=[[("📜 Задания", "quests")], [("◀️ В мир", "world")]])


# ── экраны ──────────────────────────────────────────────────

def journal(p):
    """Дневник: что взято и что можно сдать."""
    refresh_daily(p)
    live = active(p)
    rows, lines = [], []
    for q in live:
        f = fields(q)
        mark = "✅" if complete(p, q) else "▫️"
        daily = " 🔄" if f["daily"] else ""
        lines.append(f"{mark} <b>{f['name']}</b>{daily}\n{goal_line(p, q)}")
        if complete(p, q):
            rows.append([(f"✅ Сдать: {f['name'][:18]}", f"qdone:{f['id']}")])
        else:
            rows.append([(f"🚮 Бросить: {f['name'][:16]}", f"qdrop:{f['id']}")])
    if not live:
        lines.append("<i>Заданий нет. Загляни к жителям Погоста — у них всегда "
                     "найдётся работа.</i>")
    rows.append([("◀️ В мир", "world"), ("◀️ Меню", "menu")])
    return Reply(text="📜 <b>Дневник заданий</b>\n\n" + "\n\n".join(lines),
                 keyboard=rows)


def offer_rows(p, npc_index):
    """Кнопки «взять задание» для диалога с NPC."""
    rows = []
    for q in available(p, npc_index):
        f = fields(q)
        tag = "🔄 " if f["daily"] else "📜 "
        rows.append([(f"{tag}{f['name']}", f"qtake:{f['id']}")])
    for q in active(p):
        f = fields(q)
        if f["npc"] == int(npc_index) and complete(p, q):
            rows.append([(f"✅ Сдать: {f['name'][:18]}", f"qdone:{f['id']}")])
    return rows


def card(p, qid):
    """Карточка задания перед принятием."""
    q = _row(qid)
    if q is None:
        return Reply(alert="Задание не найдено.")
    f = fields(q)
    return Reply(text=f"📜 <b>{f['name']}</b>\n\n<i>{f['text']}</i>\n\n{goal_line(p, q)}",
                 keyboard=[[("✔️ Взять", f"qtake:{f['id']}")],
                           [("◀️ Назад", "world")]])
