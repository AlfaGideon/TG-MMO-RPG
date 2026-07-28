"""Действия вкладки «Игроки»."""
from engine import adminbot, permissions, rules
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
    A("player-access", lambda arg: app.modal(page.access_form(app, arg)))
    A("access-preset", lambda arg: _preset(app, arg))
    A("access-newpass", lambda arg: _newpass(app, arg))
    A("access-save", lambda arg: _access_save(app, arg))
    A("access-revoke", lambda arg: _access_revoke(app, arg))


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
    p = _get(app, tg_id)
    if not p:
        return
    p.web_admin_password = permissions.new_password()
    app.store.save_player(p)
    app.modal(page.access_form(app, tg_id))
    dom.toast("Пароль сгенерирован")


def _access_save(app, tg_id):
    p = _get(app, tg_id)
    if not p:
        return
    rank = dom.value("#acc_rank", "viewer")
    caps = _checked_caps()
    if not caps:
        dom.toast("Отметь хотя бы одно право", "err")
        return

    keep = bool(p.web_admin_password)
    text = adminbot.grant(app.store, p, rank, caps, reset_password=not keep)
    app.close_modal()
    dom.toast(f"Доступ выдан: {permissions.rank_title(rank)}")
    app.render()
    _notify(app, p, text)


def _access_revoke(app, tg_id):
    p = _get(app, tg_id)
    if not p:
        return
    text = adminbot.revoke(app.store, p)
    app.close_modal()
    dom.toast("Доступ отозван")
    app.render()
    _notify(app, p, text)


def _notify(app, p, text):
    """Шлёт игроку сообщение в бот, если бот запущен."""
    if not getattr(app.bot, "running", False):
        app.log("sys", f"Бот остановлен — {p.name} узнает о доступе при запуске бота")
        return
    import asyncio

    async def send():
        res = await app.bot.call("sendMessage", chat_id=p.tg_id, text=text,
                                 parse_mode="HTML")
        if res.get("ok"):
            p.admin_notified = True
            app.store.save_player(p)
            app.log("out", f"Доступ: уведомлён {p.name}")
        else:
            app.log("err", f"Не доставлено {p.name}: {res.get('description', '?')}")

    asyncio.ensure_future(send())
