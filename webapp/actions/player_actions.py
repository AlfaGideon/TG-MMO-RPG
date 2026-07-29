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
    A("player-edit", lambda arg: _edit(app, arg))
    A("player-save", lambda arg: _save(app, arg))
    A("player-inline", lambda arg: _inline(app, arg))
    A("player-del", lambda arg: _delete(app, arg))
    A("player-heal", lambda arg: _heal(app, arg))
    A("player-give", lambda arg: _give(app, arg))
    A("players-wipe", lambda _="": _wipe(app))
    A("player-access", lambda arg: app.modal(page.access_form(app, arg)))
    A("players-page", lambda arg: _set_page(app, arg))
    A("players-sort", lambda arg: _set_sort(app, arg))
    A("players-select-all", lambda _="": _select_all_players(app))
    A("players-select-all-header", lambda _="": _select_all_players(app))
    A("players-mass-vip", lambda _="": _mass_vip(app))
    A("player-vip", lambda arg: _toggle_vip(app, arg))
    A("players-mass-del", lambda _="": _mass_delete(app))
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


def _edit(app, tg_id):
    app.state["player_ctx"] = tg_id
    app.modal(page.edit_form(app, tg_id))


def _inline(app, payload):
    try:
        tg_id, field, val = payload.rsplit(":", 2)
        tg_id = int(tg_id)
        val = int(val)
    except (ValueError, TypeError):
        dom.toast("Некорректное значение", "err")
        return
    if field not in INT_FIELDS:
        return
    if _guard(app, adminops.set_fields, tg_id, {field: val}) is None:
        return
    dom.toast("Сохранено")
    app.render()


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


def _set_sort(app, arg):
    current = app.state.get("players_sort", "level")
    order = app.state.get("players_order", "desc")
    if current == arg:
        app.state["players_order"] = "asc" if order == "desc" else "desc"
    else:
        app.state["players_sort"] = arg
        app.state["players_order"] = "desc"
    app.state["players_page"] = 1
    app.render()


def _selected_tg_ids(app):
    from js import document
    boxes = document.querySelectorAll(".player-check:checked")
    return [int(b.value) for b in boxes]


def _select_all_players(app):
    from js import document, updatePlayersMassCount
    boxes = list(document.querySelectorAll(".player-check"))
    if not boxes:
        return
    new_state = not all(b.checked for b in boxes)
    for b in boxes:
        b.checked = new_state
    header = document.querySelector("[data-act='players-select-all-header']")
    bar = document.querySelector("[data-act='players-select-all']")
    if header is not None:
        header.checked = new_state
    if bar is not None:
        bar.checked = new_state
    updatePlayersMassCount()


def _toggle_vip(app, tg_id):
    """Включить/снять VIP у одного игрока. VIP расширяет защищённый карман."""
    from engine import stash

    p = app.store.players.get(int(tg_id))
    if p is None:
        dom.toast("Игрок не найден", "err")
        return
    if stash.is_vip(p):
        stash.revoke_vip(p)
        msg = f"VIP снят у {p.name} — карман снова {stash.SLOTS}"
    else:
        stash.grant_vip(p, 30)
        msg = f"👑 VIP на 30 дней: {p.name} — карман {stash.capacity(p)}"
    app.store.save()
    app.close_modal()
    dom.toast(msg)
    app.render()


def _mass_vip(app):
    """Выдать VIP на неделю. Раньше писалось поле vip_days, которого нет
    в модели, — статус не переживал перезагрузку."""
    from engine import stash

    ids = _selected_tg_ids(app)
    if not ids:
        dom.toast("Никто не выбран", "err")
        return
    for tg_id in ids:
        p = app.store.players.get(tg_id)
        if p is not None:
            stash.grant_vip(p, 7)
    app.store.save()
    dom.toast(f"👑 VIP на 7 дней выдан: {len(ids)} — карман +{stash.VIP_BONUS}")
    app.render()


def _mass_delete(app):
    from js import window
    ids = _selected_tg_ids(app)
    if not ids:
        dom.toast("Никто не выбран", "err")
        return
    if not window.confirm(f"Удалить {len(ids)} игроков?"):
        return
    for tg_id in ids:
        _guard(app, adminops.delete_player, tg_id)
    dom.toast(f"Удалено {len(ids)} игроков")
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
