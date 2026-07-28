"""Действия вкладки «Действия админов»."""
from engine import audit
from webapp import dom


def register(app, A):
    A("audit-src", lambda arg: _src(app, arg))
    A("audit-who", lambda _="": _who(app))
    A("audit-clear", lambda _="": _clear(app))


def _src(app, src):
    app.state["audit_src"] = "" if src in ("all", "") else src
    app.render()


def _who(app):
    app.state["audit_who"] = dom.value("#auditWho", "0")
    app.render()


def _clear(app):
    from js import window
    if not window.confirm("Очистить журнал действий? История будет потеряна."):
        return
    audit.clear(app.store)
    dom.toast("Журнал очищен")
    app.render()
