"""Действия вкладки «Игроки»."""
from engine import rules
from webapp import dom
from webapp.pages import players as page

INT_FIELDS = ["level", "gold", "hp", "max_hp", "mp", "max_mp", "strength",
              "agility", "intelligence", "endurance", "luck", "x", "y"]


def register(app, A):
    A("player-edit", lambda arg: app.modal(page.edit_form(app, arg)))
    A("player-save", lambda arg: _save(app, arg))
    A("player-del", lambda arg: _delete(app, arg))
    A("player-heal", lambda arg: _heal(app, arg))
    A("player-give", lambda arg: _give(app, arg))
    A("players-wipe", lambda _="": _wipe(app))


def _get(app, tg_id):
    return app.store.players.get(int(tg_id))


def _save(app, tg_id):
    p = _get(app, tg_id)
    if not p:
        return
    p.name = dom.value("#pf_name", p.name)
    for k in INT_FIELDS + ["loc"]:
        try:
            setattr(p, k, int(dom.value(f"#pf_{k}", getattr(p, k))))
        except (ValueError, TypeError):
            pass
    
    node_admin = dom.el("#pf_is_admin")
    p.is_web_admin = bool(node_admin.checked) if node_admin is not None else False
    p.web_admin_role = dom.value("#pf_role", "viewer")

    app.store.save_player(p)
    app.close_modal()
    dom.toast("Сохранено")
    app.render()


def _heal(app, tg_id):
    p = _get(app, tg_id)
    if not p:
        return
    s = rules.stats(p)
    p.hp, p.mp = s["max_hp"], s["max_mp"]
    app.store.save_player(p)
    app.close_modal()
    dom.toast(f"{p.name} исцелён")
    app.render()


def _give(app, tg_id):
    p = _get(app, tg_id)
    if not p:
        return
    idx = int(dom.value("#pf_give", "0"))
    p.inventory.append(idx)
    app.store.save_player(p)
    app.modal(page.edit_form(app, tg_id))
    dom.toast(f"Выдан: {rules.item(idx)['name']}")


def _delete(app, tg_id):
    app.store.players.pop(int(tg_id), None)
    app.store.save()
    dom.toast("Игрок удалён")
    app.render()


def _wipe(app):
    from js import window
    if not window.confirm("Удалить всех игроков?"):
        return
    app.store.wipe_players()
    dom.toast("Игроки удалены")
    app.render()
