"""Роутер экономики: мастерская, заточка и аукцион.

Вынесено из `engine/game.py`, чтобы роутер не разрастался. Здесь только
разбор действий и склейка Reply — вся логика живёт в `engine/craft.py`
и `engine/auction.py`.
"""
from engine import auction, craft

# Действия, которые обрабатывает этот модуль
ACTIONS = ("craft", "mk", "sharpen", "shrp",
           "auc", "auclot", "aucbuy", "aucmine", "aucnew", "aucput",
           "aucoff", "aucnpc")


def handles(head):
    return head in ACTIONS


def route(store, p, head, arg):
    """Возвращает Reply или None, если действие не наше."""
    fn = _ROUTES.get(head)
    return fn(store, p, arg) if fn else None


# ── мастерская ──────────────────────────────────────────────

def _craft(store, p, arg):
    if arg:
        return craft.station_view(store, p, arg)
    return craft.workshop(store, p)


def _make(store, p, arg):
    inst, msg = craft.craft(store, p, int(arg))
    r = craft.station_view(store, p, craft.recipe(int(arg))[2])
    r.alert = ("🔨 " + msg) if inst else msg
    return r


def _sharpen(store, p, arg):
    return craft.sharpen_view(store, p, arg or 0)


def _upgrade(store, p, arg):
    ok, msg = craft.upgrade(store, p, arg)
    r = craft.sharpen_view(store, p, 0)
    r.alert = ("⚡ " + msg) if ok else msg
    return r


# ── аукцион ─────────────────────────────────────────────────

def _board(store, p, arg):
    return auction.board(store, p, arg or 0)


def _lot(store, p, arg):
    return auction.lot_card(store, p, arg)


def _buy(store, p, arg):
    ok, msg = auction.buy(store, p, arg)
    r = auction.board(store, p, 0)
    r.alert = ("🔁 " + msg) if ok else msg
    return r


def _mine(store, p, arg):
    return auction.my_lots(store, p)


def _new(store, p, arg):
    return auction.sell_form(store, p, arg)


def _put(store, p, arg):
    uid, _, price = str(arg).partition(":")
    lot, msg = auction.list_item(store, p, uid, price or 0)
    r = auction.my_lots(store, p)
    r.alert = ("📢 " + msg) if lot else msg
    return r


def _off(store, p, arg):
    _ok, msg = auction.cancel(store, p, arg)
    r = auction.my_lots(store, p)
    r.alert = msg
    return r


def _npc(store, p, arg):
    ok, msg = auction.sell_to_npc(store, p, arg)
    r = auction.my_lots(store, p)
    r.alert = ("🤝 " + msg) if ok else msg
    return r


_ROUTES = {
    "craft": _craft, "mk": _make, "sharpen": _sharpen, "shrp": _upgrade,
    "auc": _board, "auclot": _lot, "aucbuy": _buy, "aucmine": _mine,
    "aucnew": _new, "aucput": _put, "aucoff": _off, "aucnpc": _npc,
}
