"""Социальные экраны: отряд, надгробия и задания.

Тонкая обёртка над engine.party / engine.death / engine.quests, чтобы
роутер `engine/game.py` оставался списком команд, а не свалкой логики.
Здесь только то, что нужно всем трём: сохранить игрока после действия.
"""
from engine import (death, dungeon, factions, landmarks, party, quests,
                    stash, worldboss)
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


# ── подземелья ──────────────────────────────────────────────

def dungeon_enter(store, p):
    return dungeon.enter(store, p)


def dungeon_view(store, p):
    return dungeon.view(store, p)


def dungeon_move(store, p, direction):
    return dungeon.move(store, p, direction)


def dungeon_fight(store, p):
    return dungeon.fight(store, p)


def dungeon_chest(store, p):
    return dungeon.open_chest(store, p)


def dungeon_down(store, p):
    return dungeon.descend(store, p)


def dungeon_exit(store, p):
    return dungeon.leave(store, p)


def dungeon_map(store, p):
    return dungeon.minimap(store, p)


def in_dungeon(p):
    return dungeon.inside(p)


# ── репутация ───────────────────────────────────────────────

def reputation(store, p):
    return factions.card(store, p)


# ── мировой босс ────────────────────────────────────────────

def boss_alive(store):
    return worldboss.active(store) is not None


def boss(store, p):
    return worldboss.card(store, p)


def boss_hit(store, p):
    return worldboss.strike(store, p)


# ── достопримечательности ───────────────────────────────────

def study(store, p, cell):
    return landmarks.claim(store, p, cell)


# ── защищённый карман ───────────────────────────────────────

def stash_view(store, p):
    return stash.view(p, store=store)


def stash_put(store, p, pos):
    r = stash.put(p, pos, store=store)
    store.save_player(p)
    return r


def stash_take(store, p, pos):
    r = stash.take(p, pos, store=store)
    store.save_player(p)
    return r


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
