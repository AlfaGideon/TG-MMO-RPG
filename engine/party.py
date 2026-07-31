"""Отряды: повод звать друзей.

До этого играть вместе было нельзя — взаимодействие исчерпывалось аукционом
и таблицей топа. Отряд до `MAX_SIZE` героев даёт общую добычу и делает
подземелья и боссов осмысленными.

Как устроено. Отряд — запись в настройках (общая для бота и панели):
`{"id", "leader", "members": [tg_id], "created"}`. Игрок состоит максимум
в одном. Приглашение кладётся приглашённому в `p.party_invite` и ждёт
ответа — навязать участие нельзя.

Делёж награды. Опыт и золото за победу получают все, кто **в той же
локации** (иначе можно было бы «возить» друга по миру, стоя в городе).
Каждому достаётся полная доля плюс бонус за игру вместе — но общий фонд
ограничен `MAX_TOTAL`, чтобы отряд не превращался в станок по печати денег.
"""
import time

from engine import money
from engine.models import Reply

PARTIES = "parties"
MAX_SIZE = 3                 # больше — уже толпа, бой станет нечитаемым
TOGETHER_BONUS = 0.15        # +15% каждому за игру в отряде
MAX_TOTAL = 2.0              # суммарно отряд не получит больше, чем ×2


# ── хранилище ───────────────────────────────────────────────

def _all(store):
    lst = store.settings.get(PARTIES)
    if not isinstance(lst, list):
        lst = []
        store.settings[PARTIES] = lst
    return lst


def of(store, p):
    """Отряд игрока или None."""
    for party in _all(store):
        if int(p.tg_id) in [int(m) for m in party.get("members", [])]:
            return party
    return None


def members(store, p, same_loc=None):
    """Соратники игрока (без него самого). `same_loc` — только рядом."""
    party = of(store, p)
    if not party:
        return []
    out = []
    for tg_id in party.get("members", []):
        if int(tg_id) == int(p.tg_id):
            continue
        q = store.players.get(int(tg_id))
        if q is None or not q.created_char:
            continue
        if same_loc is not None and q.loc != same_loc:
            continue
        out.append(q)
    return out


def is_leader(store, p):
    party = of(store, p)
    return bool(party and int(party.get("leader", 0)) == int(p.tg_id))


# ── создание и приглашения ──────────────────────────────────

def create(store, p):
    if of(store, p):
        return Reply(alert="Ты уже в отряде.")
    party = {"id": int(time.time() * 1000) % 10_000_000,
             "leader": int(p.tg_id), "members": [int(p.tg_id)],
             "created": int(time.time())}
    _all(store).append(party)
    store.save()
    return card(store, p)


def invite(store, p, name_or_id):
    """Позвать героя по имени или Telegram ID."""
    party = of(store, p) or None
    if party is None:
        create(store, p)
        party = of(store, p)
    if int(party.get("leader", 0)) != int(p.tg_id):
        return Reply(alert="Звать в отряд может только предводитель.")
    if len(party.get("members", [])) >= MAX_SIZE:
        return Reply(alert=f"В отряде уже {MAX_SIZE} героя — больше некуда.")

    target = _find(store, name_or_id)
    if target is None:
        return Reply(alert="Такого героя нет.")
    if int(target.tg_id) == int(p.tg_id):
        return Reply(alert="Себя звать не нужно.")
    if of(store, target):
        return Reply(alert=f"{target.name} уже в отряде.")

    target.party_invite = int(party["id"])
    store.save_player(target)
    _tell(store, target.tg_id,
          f"🤝 <b>{p.name}</b> зовёт тебя в отряд!\n"
          f"Открой «🤝 Отряд» в меню, чтобы принять или отказаться.")
    return Reply(text=f"📨 Приглашение отправлено: <b>{target.name}</b>.",
                 keyboard=[[("🤝 Отряд", "party")], [("◀️ В мир", "world")]])


def _find(store, needle):
    needle = str(needle).strip().lower()
    if not needle:
        return None
    for q in store.players.values():
        if not q.created_char:
            continue
        if str(q.tg_id) == needle or q.name.lower() == needle:
            return q
    for q in store.players.values():          # частичное совпадение имени
        if q.created_char and needle in q.name.lower():
            return q
    return None


def accept(store, p):
    pid = int(getattr(p, "party_invite", 0) or 0)
    if not pid:
        return Reply(alert="Тебя никто не звал.")
    party = next((x for x in _all(store) if int(x["id"]) == pid), None)
    p.party_invite = 0
    if party is None:
        store.save_player(p)
        return Reply(alert="Этот отряд уже распался.")
    if len(party["members"]) >= MAX_SIZE:
        store.save_player(p)
        return Reply(alert="Отряд уже полон.")
    party["members"].append(int(p.tg_id))
    store.save_player(p)
    for q in members(store, p):
        _tell(store, q.tg_id, f"🤝 <b>{p.name}</b> присоединился к отряду!")
    return card(store, p)


def decline(store, p):
    p.party_invite = 0
    store.save_player(p)
    return Reply(text="Ты отклонил приглашение.",
                 keyboard=[[("◀️ В мир", "world")]])


def leave(store, p):
    party = of(store, p)
    if not party:
        return Reply(alert="Ты не в отряде.")
    party["members"] = [m for m in party["members"] if int(m) != int(p.tg_id)]
    leader_left = int(party.get("leader", 0)) == int(p.tg_id)
    if len(party["members"]) < 2:             # отряд из одного смысла не имеет
        for tg_id in party["members"]:
            _tell(store, tg_id, "🤝 Отряд распался.")
        _all(store)[:] = [x for x in _all(store) if x is not party]
    elif leader_left:
        party["leader"] = int(party["members"][0])
        _tell(store, party["leader"], "🤝 Теперь ты ведёшь отряд.")
    store.save()
    return Reply(text="🚪 Ты покинул отряд.",
                 keyboard=[[("🤝 Отряд", "party")], [("◀️ В мир", "world")]])


# ── общая награда ───────────────────────────────────────────

def share(store, p, gold, exp):
    """Раздать соратникам в той же локации их долю. Возвращает строки отчёта.

    Долю получает каждый, кто рядом; фонд ограничен MAX_TOTAL, поэтому
    большой отряд не выгоднее маленького сверх меры.
    """
    from engine import rules

    mates = members(store, p, same_loc=p.loc)
    if not mates:
        return []
    part = _fund(len(mates) + 1) / (len(mates) + 1)
    lines = []
    for q in mates:
        q_gold = max(1, int(gold * part))
        q_exp = max(1, int(exp * part))
        money.earn(q, q_gold)
        levels = rules.add_exp(q, q_exp)
        store.save_player(q)
        _tell(store, q.tg_id,
              f"🤝 {p.name} бьётся рядом: {money.plus(q_gold)} +{q_exp} ⭐"
              + (f"\n🎖 Новый уровень: {q.level}!" if levels else ""))
        lines.append(f"🤝 {q.name}: {money.plus(q_gold)} +{q_exp} ⭐")
    return lines


def _fund(size):
    """Общий фонд награды на отряд из `size` героев, стоящих вместе."""
    if size < 2:
        return 1.0                        # один в поле — обычная награда
    return min(MAX_TOTAL, 1.0 + TOGETHER_BONUS * size)


def bonus(store, p):
    """Множитель награды самого игрока: его доля из общего фонда."""
    mates = members(store, p, same_loc=p.loc)
    if not mates:
        return 1.0                        # соратников рядом нет — как обычно
    size = len(mates) + 1
    return _fund(size) / size


# ── экраны ──────────────────────────────────────────────────

def card(store, p):
    """Экран отряда: состав, приглашение, выход."""
    pending = int(getattr(p, "party_invite", 0) or 0)
    if pending:
        party = next((x for x in _all(store) if int(x["id"]) == pending), None)
        who = store.players.get(int(party["leader"])) if party else None
        name = who.name if who else "Кто-то"
        return Reply(text=f"🤝 <b>Приглашение в отряд</b>\n\n<b>{name}</b> зовёт "
                          f"тебя в свой отряд.\n\n<i>Вместе добыча щедрее: "
                          f"+{int(TOGETHER_BONUS * 100)}% каждому, кто рядом.</i>",
                     keyboard=[[("✅ Принять", "pjoin"), ("❌ Отказаться", "pno")],
                               [("◀️ В мир", "world")]])

    party = of(store, p)
    if not party:
        return Reply(text=(
            "🤝 <b>Отряд</b>\n\nТы странствуешь в одиночку.\n\n"
            f"<i>В отряде до {MAX_SIZE} героев. Опыт и золото получают все, "
            f"кто в одной локации, и каждому идёт бонус "
            f"+{int(TOGETHER_BONUS * 100)}%.</i>\n\n"
            "Чтобы позвать: <code>/invite Имя</code> — или кнопкой ниже."),
            keyboard=[[("➕ Создать отряд", "pnew")], [("◀️ В мир", "world")]])

    lines = ["🤝 <b>Отряд</b>\n"]
    for tg_id in party["members"]:
        q = store.players.get(int(tg_id))
        if q is None:
            continue
        crown = "👑 " if int(party["leader"]) == int(tg_id) else "▫️ "
        near = "рядом" if q.loc == p.loc else "далеко"
        you = " (ты)" if int(tg_id) == int(p.tg_id) else ""
        lines.append(f"{crown}<b>{q.name}</b>{you} — ур. {q.level} · {near}")
    mates = members(store, p, same_loc=p.loc)
    if mates:
        lines.append(f"\n✨ Вместе: награда ×{_fund(len(mates) + 1):.2f} на отряд "
                     f"(каждому по {bonus(store, p) * 100:.0f}% от обычной)")
    else:
        lines.append("\n<i>Соратники в других краях — доли не будет, "
                     "пока не соберётесь вместе.</i>")

    rows = []
    if is_leader(store, p) and len(party["members"]) < MAX_SIZE:
        rows.append([("📨 Позвать: /invite Имя", "pnoop")])
    rows.append([("🚪 Покинуть отряд", "pleave")])
    rows.append([("◀️ В мир", "world")])
    return Reply(text="\n".join(lines), keyboard=rows)


def _tell(store, tg_id, text):
    """Весть соратнику через общую очередь исходящих."""
    from engine import adminops
    adminops.queue(store, int(tg_id), text)
