"""Тонкая обёртка над DOM, чтобы писать UI на Python без JS.

Управление временем жизни pyodide-прокси — то, что раньше «тормозило»
панель на долгих сессиях. Каждый `create_proxy(fn)` держит JS-обёртку
над Python-объектом; если её не освободить явно (`.destroy()`), она живёт
вечно, даже когда DOM-узел, на который она навешана, давно удалён
перерисовкой (`app.render()` вызывается почти на каждое действие в панели).
Раньше все проксирования копились в один список `_proxies` без счёта, и
за сессию с полусотней кликов набирались сотни забытых обработчиков —
отсюда «жор» памяти и дёрганый UI при длинной работе с админкой.

Прокси делятся на два времени жизни:

  * `_scoped` — навешаны на разметку текущего рендера (валидация форм,
    автосохранение, превью картинок, инлайн-редактирование). Уничтожаются
    и создаются заново в каждом `wire_forms()` — то есть при каждом
    `render()`.
  * «постоянные» — один делегированный клик-слушатель на `document`
    (`bind_actions`) и общий обработчик исчезновения тоста (`toast`).
    Создаются один раз за всё время жизни страницы.
"""
from js import document
from pyodide.ffi import create_proxy

from webapp.html import esc  # noqa: F401  (реэкспорт для страниц)

_scoped = []            # прокси текущего рендера — гасим перед следующим
_permanent = []         # прокси на весь жизненный цикл страницы
_actions = {}           # {name: callable}


def _destroy(proxy):
    """Освобождает pyodide-прокси. В тестах (стаб create_proxy) — no-op."""
    destroy = getattr(proxy, "destroy", None)
    if callable(destroy):
        try:
            destroy()
        except Exception:
            pass


def _track(proxy, bucket):
    bucket.append(proxy)
    return proxy


def _proxy_scoped(fn):
    return _track(create_proxy(fn), _scoped)


def _release_scoped():
    """Гасит прокси прошлого рендера перед тем, как навесить новые."""
    while _scoped:
        _destroy(_scoped.pop())


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
    """Разовая привязка к текущему рендеру — живёт до следующего wire_forms()."""
    node = el(sel)
    if node is None:
        return
    node.addEventListener(event, _proxy_scoped(fn))


def action(name):
    """Декоратор: регистрирует обработчик для data-act="name"."""
    def wrap(fn):
        _actions[name] = fn
        return fn
    return wrap


def register(name, fn):
    _actions[name] = fn


def bind_actions():
    """Один делегированный слушатель на весь документ. Вызывается один раз."""
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

    document.addEventListener("click", _track(create_proxy(handler), _permanent))


# ── тост: один переиспользуемый таймер, а не проксирование на каждый вызов ──
_toast_timeout_id = None
_toast_hide_proxy = None


def _toast_hide(node):
    def hide(*_):
        node.setAttribute("class", "toast")
    return hide


def toast(text, kind="ok"):
    global _toast_timeout_id, _toast_hide_proxy
    node = el("#toast")
    if node is None:
        return
    node.textContent = text
    node.className = f"toast show {kind}"
    from js import clearTimeout, setTimeout
    if _toast_timeout_id is not None:
        clearTimeout(_toast_timeout_id)
    if _toast_hide_proxy is None:                     # создаём прокси один раз
        _toast_hide_proxy = _track(create_proxy(_toast_hide(node)), _permanent)
    _toast_timeout_id = setTimeout(_toast_hide_proxy, 2600)


def wire_forms():
    """Подключает клиентскую валидацию и автосохранение черновиков форм.

    Вызывается после каждого `render()`. Сначала гасит прокси прошлого
    рендера (`_release_scoped`) — иначе на разметку, которую только что
    заменил `innerHTML`, продолжают ссылаться обработчики со старых,
    уже отсоединённых от DOM узлов.
    """
    from js import window
    _release_scoped()

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
                inp.addEventListener("input", _proxy_scoped(lambda evt, i=inp: validate_input(i)))
            form.addEventListener("submit", _proxy_scoped(lambda evt, f=form: validate_form(f)))
        if form.hasAttribute("data-autosave"):
            for inp in form.querySelectorAll("input, select, textarea"):
                inp.addEventListener("input", _proxy_scoped(lambda evt, f=form: save_draft(f)))
            restore_draft(form)
            form.addEventListener(
                "submit",
                _proxy_scoped(lambda evt, f=form: window.localStorage.removeItem(
                    "draft:" + (f.getAttribute("id") or f.action or "form"))))

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
            reader.addEventListener("load", _proxy_scoped(done))
            reader.readAsDataURL(files.item(0))
        inp.addEventListener("change", _proxy_scoped(onchange))

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
        submit_proxy = _proxy_scoped(make_submit(form))
        inp.addEventListener("change", submit_proxy)

        def make_key(p):
            def key(evt):
                if evt.key == "Enter":
                    p(evt)
            return key
        inp.addEventListener("keydown", _proxy_scoped(make_key(submit_proxy)))
