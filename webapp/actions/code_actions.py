"""Действия для многоязычной песочницы кода.

Pyodide исполняет только Python — это ограничение самого CPython в WASM,
а не поломка. Поэтому JS / C++ / Ruby запускаются отдельными браузерными
рантаймами, реализованными в webapp/static/interactions.js (window.__runCode,
возвращает Promise). Python здесь исполняется напрямую через уже загруженный
Pyodide (window.__py.runPython) с перехватом sys.stdout, чтобы показать вывод.
"""
from webapp import dom


def register(app, A):
    A("run-code", lambda *_arg: _run_code(app))


async def _run_code(app):
    from js import document
    lang_el = document.querySelector('select[name="code-lang"]')
    code_el = document.querySelector('textarea[name="code"]')
    lang = str(lang_el.value) if lang_el is not None else "python"
    code = str(code_el.value) if code_el is not None else ""
    app.state["code_lang"] = lang
    app.state["code"] = code
    app.state["code_output"] = "⏳ Выполняется…"
    app.render()
    try:
        result = await _execute(lang, code)
    except Exception as exc:                        # не роняем панель
        import traceback
        traceback.print_exc()
        result = "❌ Ошибка исполнения: " + str(exc)
    app.state["code_output"] = result
    app.render()


async def _execute(lang, code):
    """Исполнить код на выбранном языке и вернуть строку вывода."""
    if lang == "python":
        return _run_python(code)
    # Остальные языки живут в static JS (браузерные рантаймы). Вызов
    # возвращает JsProxy промиса; `await` раскрывает его в строку.
    from js import window
    promise = window.__runCode(lang, code)
    result = await promise
    return str(result) if result is not None else ""


def _run_python(code):
    """Запустить Python через уже загруженный Pyodide, захватив stdout."""
    import io
    import sys
    from js import window

    py = getattr(window, "__py", None)
    if py is None:
        return "❌ Среда Python ещё не инициализирована."

    buf = io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = buf, buf
    try:
        result = py.runPython(code)
    except Exception as exc:
        import traceback
        buf.write("Traceback (most recent call last):\n")
        buf.write(traceback.format_exc())
        result = None
    finally:
        sys.stdout, sys.stderr = old_out, old_err

    out = buf.getvalue()
    if result is not None:
        try:
            out += ("" if out.endswith("\n") or not out else "\n") + repr(result) + "\n"
        except Exception:
            pass
    return out if out else "(пустой вывод)"
