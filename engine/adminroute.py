"""Роутер админ-действий в боте: callback `adm:<команда>:<аргументы>`."""
from engine import adminmenu, adminops
from engine.models import Reply

SRC = "bot"


def handle(p, store, arg):
    """arg — часть callback после `adm:`. Возвращает Reply."""
    if not p.is_web_admin:
        return Reply(alert="У тебя нет доступа к админке.")
    head, _, rest = (arg or "").partition(":")
    fn = ROUTES.get(head)
    if fn is None:
        return Reply(alert="Неизвестное действие админки.")
    try:
        return fn(p, store, rest)
    except adminops.Denied as e:
        return Reply(alert=str(e))
    except Exception as e:                                    # не роняем бота
        return Reply(alert=f"Ошибка: {e}")


def text_input(p, store, text):
    """Ожидаемый от админа свободный текст (сейчас — тело рассылки)."""
    if getattr(p, "pending", "") != "broadcast":
        return None
    p.pending = ""
    store.save_player(p)
    body = (text or "").strip()
    if not body:
        return Reply(text="Пустое сообщение — рассылка отменена.",
                     keyboard=[[("◀️ Админка", "admin")]])
    try:
        _, n = adminops.broadcast(store, p, body, SRC)
    except adminops.Denied as e:
        return Reply(text=f"❌ {e}", keyboard=[[("◀️ Админка", "admin")]])
    return Reply(text=f"📣 Рассылка поставлена в очередь: <b>{n}</b> получателей.",
                 keyboard=[[("📜 Журнал", "adm:audit:0")], [("◀️ Админка", "admin")]],
                 new_message=True)


def _int(rest, default=0):
    try:
        return int(str(rest).split(":")[0])
    except (ValueError, IndexError):
        return default


# ── экраны ──────────────────────────────────────────────────

def _stats(p, store, rest):
    return adminmenu.stats(p, store)


def _players(p, store, rest):
    return adminmenu.players(p, store, _int(rest))


def _card(p, store, rest):
    return adminmenu.player_card(p, store, _int(rest))


def _gift(p, store, rest):
    return adminmenu.gift_menu(p, store, _int(rest))


def _grant_menu(p, store, rest):
    return adminmenu.grant_menu(p, store, _int(rest))


def _portals(p, store, rest):
    return adminmenu.portals(p, store)


def _content(p, store, rest):
    return adminmenu.content(p, store)


def _cata(p, store, rest):
    return adminmenu.cataclysms(p, store)


def _cata_hit(p, store, rest):
    """Удар из бота: бедствие по случайной локации, срок по умолчанию."""
    kind_key = str(rest).split(":")[0]
    adminops.cataclysm_strike(store, p, kind_key, adminmenu.pick_loc(store),
                              source=SRC)
    return adminmenu.cataclysms(p, store)


def _cata_off(p, store, rest):
    adminops.cataclysm_end(store, p, _int(rest), source=SRC)
    return adminmenu.cataclysms(p, store)


def _audit(p, store, rest):
    return adminmenu.audit_log(p, store, _int(rest))


def _cast(p, store, rest):
    from engine import permissions
    if not permissions.can(p, "broadcast"):
        return Reply(alert="Нет права на рассылку.")
    p.pending = "broadcast"
    store.save_player(p)
    return Reply(text=("📣 <b>Рассылка игрокам</b>\n\n"
                       "Пришли следующим сообщением текст — я разошлю его всем.\n"
                       "HTML разрешён. Отмена — кнопка ниже."),
                 keyboard=[[("✖️ Отмена", "adm:castoff")], [("◀️ Админка", "admin")]])


def _cast_off(p, store, rest):
    p.pending = ""
    store.save_player(p)
    return Reply(text="Рассылка отменена.", keyboard=[[("◀️ Админка", "admin")]])


def _noop(p, store, rest):
    return Reply(alert="")


# ── действия ────────────────────────────────────────────────

def _heal(p, store, rest):
    adminops.heal(store, p, _int(rest), SRC)
    r = adminmenu.player_card(p, store, _int(rest))
    r.alert = "Игрок исцелён"
    return r


def _give(p, store, rest):
    parts = str(rest).split(":")
    tg_id, idx = _int(parts[0]), _int(parts[1] if len(parts) > 1 else 0)
    _, info = adminops.give_item(store, p, tg_id, idx, SRC)
    r = adminmenu.player_card(p, store, tg_id)
    r.alert = f"Выдано: {info}"
    return r


def _gold(p, store, rest):
    parts = str(rest).split(":")
    tg_id, amount = _int(parts[0]), _int(parts[1] if len(parts) > 1 else 0)
    adminops.add_gold(store, p, tg_id, amount, SRC)
    r = adminmenu.player_card(p, store, tg_id)
    r.alert = f"Золото: {amount:+d}"
    return r


def _level(p, store, rest):
    parts = str(rest).split(":")
    tg_id, delta = _int(parts[0]), _int(parts[1] if len(parts) > 1 else 0)
    adminops.add_level(store, p, tg_id, delta, SRC)
    r = adminmenu.player_card(p, store, tg_id)
    r.alert = f"Уровень: {delta:+d}"
    return r


def _tp(p, store, rest):
    from engine import world as W
    tg_id = _int(rest)
    adminops.teleport(store, p, tg_id, 0, W.SPAWN[0], W.SPAWN[1], SRC)
    r = adminmenu.player_card(p, store, tg_id)
    r.alert = "Игрок телепортирован в деревню"
    return r


def _del(p, store, rest):
    tg_id = _int(rest)
    adminops.delete_player(store, p, tg_id, SRC)
    r = adminmenu.players(p, store, 0)
    r.alert = "Игрок удалён"
    return r


def _rank(p, store, rest):
    parts = str(rest).split(":")
    tg_id = _int(parts[0])
    rank = parts[1] if len(parts) > 1 else "viewer"
    adminops.grant(store, p, tg_id, rank, None, SRC)
    r = adminmenu.player_card(p, store, tg_id)
    r.alert = "Доступ выдан"
    return r


def _revoke(p, store, rest):
    tg_id = _int(rest)
    adminops.revoke(store, p, tg_id, SRC)
    r = adminmenu.player_card(p, store, tg_id)
    r.alert = "Доступ отозван"
    return r


def _newpass(p, store, rest):
    tg_id = _int(rest)
    adminops.new_password(store, p, tg_id, SRC)
    q = store.players.get(tg_id)
    r = adminmenu.player_card(p, store, tg_id)
    r.alert = f"Новый пароль: {q.web_admin_password}" if q else "Готово"
    return r


def _portal_open(p, store, rest):
    _, info = adminops.portal_open(store, p, _int(rest), adminmenu.pick_cell, SRC)
    r = adminmenu.portals(p, store)
    r.alert = f"Портал открыт: {info}"
    return r


def _portal_close(p, store, rest):
    adminops.portal_close(store, p, _int(rest), SRC)
    r = adminmenu.portals(p, store)
    r.alert = "Портал закрыт"
    return r


ROUTES = {
    "stats": _stats, "players": _players, "p": _card, "gift": _gift,
    "grant": _grant_menu, "portals": _portals, "content": _content,
    "audit": _audit, "cast": _cast, "castoff": _cast_off, "noop": _noop,
    "heal": _heal, "give": _give, "gold": _gold, "lvl": _level, "tp": _tp,
    "del": _del, "rank": _rank, "revoke": _revoke, "pass": _newpass,
    "popen": _portal_open, "pclose": _portal_close,
    "cata": _cata, "catahit": _cata_hit, "cataoff": _cata_off,
}
