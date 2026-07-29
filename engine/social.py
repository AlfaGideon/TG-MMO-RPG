"""Социальные экраны: отряд, надгробия и задания.

Тонкая обёртка над engine.party / engine.death / engine.quests, чтобы
роутер `engine/game.py` оставался списком команд, а не свалкой логики.
Здесь только то, что нужно всем трём: сохранить игрока после действия.
"""
from engine import death, party, quests
from engine.models import Reply


# ── отряд ───────────────────────────────────────────────────

def party_card(store, p):
    return party.card(store, p)


def party_new(store, p):
    return party.create(store, p)


def party_join(store, p):
    return party.accept(store, p)


def party_no(store, p):
    return party.decline(store, p)


def party_leave(store, p):
    return party.leave(store, p)


def party_invite(store, p, name):
    return party.invite(store, p, name)


def party_hint():
    return Reply(alert="Отправь: /invite Имя героя")


# ── надгробия ───────────────────────────────────────────────

def grave(store, p):
    return death.grave_card(store, p)


def claim(store, p):
    return death.claim(store, p)


# ── задания ─────────────────────────────────────────────────

def on_enter(p, loc):
    """Приход в локацию засчитывает задания-разведки."""
    return quests.on_enter(p, loc)


def journal(p):
    return quests.journal(p)


def quest_take(store, p, qid):
    r = quests.take(p, qid)
    store.save_player(p)
    return r


def quest_drop(store, p, qid):
    r = quests.abandon(p, qid)
    store.save_player(p)
    return r


def quest_done(store, p, qid):
    return quests.hand_in(store, p, qid)


def quest_card(p, qid):
    return quests.card(p, qid)
