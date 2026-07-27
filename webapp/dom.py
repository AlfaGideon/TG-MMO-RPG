"""Тонкая обёртка над DOM, чтобы писать UI на Python без JS."""
from js import document
from pyodide.ffi import create_proxy

from webapp.html import esc  # noqa: F401  (реэкспорт для страниц)

_proxies = []          # держим ссылки, иначе pyodide освободит колбэки
_actions = {}          # {name: callable}


def el(sel):
    return document.querySelector(sel)


def html(sel, markup):
    node = el(sel)
    if node is not None:
        node.innerHTML = markup
    return node


def value(sel, default=""):
    node = el(sel)
    return node.value if node is not None else default


def set_value(sel, val):
    node = el(sel)
    if node is not None:
        node.value = val


def on(sel, event, fn):
    node = el(sel)
    if node is None:
        return
    proxy = create_proxy(fn)
    _proxies.append(proxy)
    node.addEventListener(event, proxy)


def action(name):
    """Декоратор: регистрирует обработчик для data-act="name"."""
    def wrap(fn):
        _actions[name] = fn
        return fn
    return wrap


def register(name, fn):
    _actions[name] = fn


def bind_actions():
    """Один делегированный слушатель на весь документ."""
    import asyncio

    def handler(evt):
        target = getattr(evt, "target", None)
        if target is None or not hasattr(target, "closest"):
            return
        node = target.closest("[data-act]")
        if node is None:
            return
        fn = _actions.get(node.getAttribute("data-act"))
        if fn is None:
            return
        evt.preventDefault()
        arg = node.getAttribute("data-arg") or ""
        try:
            res = fn(arg)
        except Exception as exc:                      # не роняем весь UI
            toast(f"Ошибка: {exc}", "err")
            import traceback
            traceback.print_exc()
            return
        if hasattr(res, "__await__"):
            asyncio.ensure_future(_guard(res))

    async def _guard(coro):
        try:
            await coro
        except Exception as exc:
            toast(f"Ошибка: {exc}", "err")
            import traceback
            traceback.print_exc()

    proxy = create_proxy(handler)
    _proxies.append(proxy)
    document.addEventListener("click", proxy)


def toast(text, kind="ok"):
    node = el("#toast")
    if node is None:
        return
    node.textContent = text
    node.className = f"toast show {kind}"
    from js import setTimeout
    setTimeout(create_proxy(lambda *_: node.setAttribute("class", "toast")), 2600)
