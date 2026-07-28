"""Действия вкладки «Игроки». Вся работа — через engine.adminops,
тот же слой, что использует бот. Поэтому права, уведомления игрокам
и журнал действий одинаковы с обеих сторон."""
from engine import adminops, permissions
from webapp import dom
from webapp.pages import players as page

INT_FIELDS = ["level", "gold", "hp", "max_hp", "mp", "max_mp", "strength",
              "agility", "intelligence", "endurance", "luck", "x", "y"]


def register(app, A):
    A("dash-heal", lambda _="": _heal_all(app))
    A("player-edit", lambda arg: app.modal(page.edit_form(app, arg)))
    A("player-save", lambda arg: _save(app, arg))
    A("player-del", lambda arg: _delete(app, arg))
    A("player-heal", lambda arg: _heal(app, arg))
    A("player-give", lambda arg: _give(app, arg))
    A("players-wipe", lambda _="": _wipe(app))
    A("player-access", lambda arg: app.modal(page.access_form(app, arg)))
    A("players-page", lambda arg: _set_page(app, arg))
    A("access-preset", lambda arg: _preset(app, arg))
    A("access-newpass", lambda arg: _newpass(app, arg))
    A("access-save", lambda arg: _access_save(app, arg))
    A("access-revoke", lambda arg: _access_revoke(app, arg))


def _guard(app, fn, *a, **kw):
    """Выполняет операцию, показывая отказ по правам тостом."""
    try:
        return fn(app.store, app.actor, *a, **kw)
    except adminops.Denied as e:
        dom.toast(str(e), "err")
        return None


def _flush(app):
    """Просит бота разослать уведомления, накопленные операцией."""
    if not getattr(app.bot, "running", False):
        app.log("sys", "Бот остановлен — уведомления уйдут после запуска")
        return
    import asyncio
    asyncio.ensure_future(app.bot.flush_outbox())


def _save(app, tg_id):
    p = app.store.players.get(int(tg_id))
    if not p:
        return
    fields = {"name": dom.value("#pf_name", p.name)}
    for k in INT_FIELDS + ["loc"]:
        try:
            fields[k] = int(dom.value(f"#pf_{k}", getattr(p, k)))
        except (ValueError, TypeError):
            pass
    if _guard(app, adminops.set_fields, tg_id, fields) is None:
        return
    app.close_modal()
    dom.toast("Сохранено")
    app.render()


def _heal(app, tg_id):
    if _guard(app, adminops.heal, tg_id) is None:
        return
    app.close_modal()
    dom.toast("Игрок исцелён")
    app.render()
    _flush(app)


def _heal_all(app):
    if not app.can("heal_players"):
        dom.toast("Недостаточно прав", "err")
        return
    for p in app.store.players.values():
        p.hp = p.max_hp
        p.mp = p.max_mp
    app.store.save()
    dom.toast("Все игроки вылечены")
    app.render()


def _give(app, tg_id):
    idx = int(dom.value("#pf_give", "0"))
    res = _guard(app, adminops.give_item, tg_id, idx)
    if res is None:
        return
    app.modal(page.edit_form(app, tg_id))
    dom.toast(f"Выдан: {res[1]}")
    _flush(app)


def _set_page(app, arg):
    app.state["players_page"] = int(arg)
    app.render()


def _delete(app, tg_id):
    if _guard(app, adminops.delete_player, tg_id) is None:
        return
    dom.toast("Игрок удалён")
    app.render()


def _wipe(app):
    from js import window
    if not window.confirm("Удалить всех игроков?"):
        return
    if _guard(app, adminops.wipe_players) is None:
        return
    dom.toast("Игроки удалены")
    app.render()


# ── доступ к админке ────────────────────────────────────────

def _checked_caps():
    """Считывает галочки функций из формы доступа."""
    out = []
    for key in permissions.CAP_KEYS:
        node = dom.el(f"#cap_{key}")
        if node is not None and node.checked:
            out.append(key)
    return out


def _preset(app, tg_id):
    """Проставляет галочки по выбранному рангу, не сохраняя."""
    rank = dom.value("#acc_rank", "viewer")
    preset = set(permissions.rank_caps(rank))
    for key in permissions.CAP_KEYS:
        node = dom.el(f"#cap_{key}")
        if node is not None:
            node.checked = key in preset
    dom.toast(f"Пресет: {permissions.rank_title(rank)}")


def _newpass(app, tg_id):
    if _guard(app, adminops.new_password, tg_id) is None:
        return
    app.modal(page.access_form(app, tg_id))
    dom.toast("Пароль сгенерирован")
    _flush(app)


def _access_save(app, tg_id):
    rank = dom.value("#acc_rank", "viewer")
    caps = _checked_caps()
    if not caps:
        dom.toast("Отметь хотя бы одно право", "err")
        return
    if _guard(app, adminops.grant, tg_id, rank, caps) is None:
        return
    app.close_modal()
    dom.toast(f"Доступ выдан: {permissions.rank_title(rank)}")
    app.render()
    _flush(app)


def _access_revoke(app, tg_id):
    if _guard(app, adminops.revoke, tg_id) is None:
        return
    app.close_modal()
    dom.toast("Доступ отозван")
    app.render()
    _flush(app)
