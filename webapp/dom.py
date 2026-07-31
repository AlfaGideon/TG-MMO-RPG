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


def wire_forms():
    """Подключает клиентскую валидацию и автосохранение черновиков форм."""
    from js import window

    def validate_input(inp):
        msg = ""
        val = inp.value.strip()
        if inp.hasAttribute("required") and not val:
            msg = "Обязательное поле"
        elif inp.type == "number" and val:
            try:
                n = float(val)
                if inp.hasAttribute("min") and n < float(inp.min):
                    msg = f"Минимум {inp.min}"
                if inp.hasAttribute("max") and n > float(inp.max):
                    msg = f"Максимум {inp.max}"
            except ValueError:
                msg = "Введите число"
        inp.setCustomValidity(msg)
        return not msg

    def validate_form(form):
        ok = True
        for inp in form.querySelectorAll("input, select, textarea"):
            if not validate_input(inp):
                ok = False
        return ok

    def save_draft(form):
        key = "draft:" + (form.getAttribute("id") or form.action or "form")
        data = {}
        for inp in form.querySelectorAll("input, select, textarea"):
            if inp.name or inp.id:
                data[inp.name or inp.id] = inp.value
        window.localStorage.setItem(key, __import__("json").dumps(data))

    def restore_draft(form):
        key = "draft:" + (form.getAttribute("id") or form.action or "form")
        raw = window.localStorage.getItem(key)
        if not raw:
            return
        try:
            data = __import__("json").loads(raw)
        except Exception:
            return
        for inp in form.querySelectorAll("input, select, textarea"):
            k = inp.name or inp.id
            if k and k in data and not inp.value:
                inp.value = data[k]

    def setup(form):
        if form.hasAttribute("data-validate"):
            for inp in form.querySelectorAll("input, select, textarea"):
                proxy = create_proxy(lambda evt, i=inp: validate_input(i))
                _proxies.append(proxy)
                inp.addEventListener("input", proxy)
            proxy = create_proxy(lambda evt, f=form: validate_form(f))
            _proxies.append(proxy)
            form.addEventListener("submit", proxy)
        if form.hasAttribute("data-autosave"):
            for inp in form.querySelectorAll("input, select, textarea"):
                proxy = create_proxy(lambda evt, f=form: save_draft(f))
                _proxies.append(proxy)
                inp.addEventListener("input", proxy)
            restore_draft(form)
            proxy = create_proxy(lambda evt, f=form: window.localStorage.removeItem("draft:" + (f.getAttribute("id") or f.action or "form")))
            _proxies.append(proxy)
            form.addEventListener("submit", proxy)

    for form in document.querySelectorAll("form[data-validate], form[data-autosave]"):
        setup(form)

    # image previews
    for inp in document.querySelectorAll("input[type=file][data-preview]"):
        target = document.querySelector(inp.getAttribute("data-preview"))
        if target is None:
            continue
        def onchange(evt, t=target):
            files = evt.target.files
            if not files or not files.length:
                return
            reader = __import__("js").FileReader.new()
            def done(e):
                t.src = e.target.result
            proxy = create_proxy(done)
            _proxies.append(proxy)
            reader.addEventListener("load", proxy)
            reader.readAsDataURL(files.item(0))
        proxy = create_proxy(onchange)
        _proxies.append(proxy)
        inp.addEventListener("change", proxy)

    # inline editing: blur or Enter saves the value
    for form in document.querySelectorAll("form.inline-form[data-act]"):
        inp = form.querySelector("input, select, textarea")
        if inp is None:
            continue
        def make_submit(f):
            def submit(evt):
                act = f.getAttribute("data-act")
                arg = f.getAttribute("data-arg") or ""
                val = evt.target.value
                fn = _actions.get(act)
                if fn is not None:
                    fn(arg + ":" + val)
            return submit
        proxy = create_proxy(make_submit(form))
        _proxies.append(proxy)
        inp.addEventListener("change", proxy)
        def make_key(p):
            def key(evt):
                if evt.key == "Enter":
                    p(evt)
            return key
        key_proxy = create_proxy(make_key(proxy))
        _proxies.append(key_proxy)
        inp.addEventListener("keydown", key_proxy)
