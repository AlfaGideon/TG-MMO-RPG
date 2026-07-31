"""Страница: многоязычная песочница кода в браузере.

Отвечает на пожелание «не вижу в Pyodide других языков»: Pyodide — это
CPython, собранный в WebAssembly, и он умеет исполнять ТОЛЬКО Python
(это свойство, а не баг). Чтобы в панели появились и другие языки, не
нужно ломать Pyodide — достаточно запускать их рядом, своими рантаймами:

  * JavaScript — нативный движок браузера (new Function + перехват console);
  * Python      — уже загруженный Pyodide (window.__py.runPython);
  * C++         — интерпретатор JSCPP (чистый JS, ~подмножество C++);
  * Ruby        — официальный ruby.wasm (WASM-сборка CRuby со stdlib).

Тяжёлые рантаймы (C++ и Ruby) грузятся лениво — только при первом
запуске — и никогда не влияют на скорость старта панели. Весь
«браузерный» код (загрузка скриптов, WebAssembly, перехват console)
живёт в webapp/static/interactions.js (см. window.__runCode), а здесь —
только разметка и передача ввода/вывода.
"""
from webapp.html import esc

TITLE = "🧪 Песочница (JS · Python · C++ · Ruby)"
CRUMBS = [("Песочница кода", "code")]

LANGS = [
    ("python", "🐍 Python (Pyodide)"),
    ("javascript", "🌐 JavaScript (браузер)"),
    ("cpp", "⚙️ C++ (JSCPP)"),
    ("ruby", "💎 Ruby (ruby.wasm)"),
]

EXAMPLES = {
    "python": """# Python выполняется в Pyodide — том же рантайме, что и вся панель.
def fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a

print("fib(10) =", fib(10))
print("Доступен и сам движок игры:")
import sys
print("Python", sys.version.split()[0])""",
    "javascript": """// JavaScript выполняется нативным движком браузера.
function sum(arr) { return arr.reduce((a, b) => a + b, 0); }

console.log("Сумма 1..5 =", sum([1, 2, 3, 4, 5]));
const user = { name: "Гидеон", level: 12 };
console.log("Игрок:", JSON.stringify(user));""",
    "cpp": """// C++ выполняется интерпретатором JSCPP (подмножество C++).
#include <iostream>
using namespace std;

int main() {
    int n = 10;
    int a = 0, b = 1;
    for (int i = 0; i < n; i++) {
        cout << a << " ";
        int t = a + b;
        a = b;
        b = t;
    }
    cout << endl;
    return 0;
}""",
    "ruby": """# Ruby выполняется официальным ruby.wasm (CRuby в WebAssembly).
def fib(n)
  return n if n < 2
  fib(n - 1) + fib(n - 2)
end

puts "fib(10) = #{fib(10)}"
puts "Привет из Ruby в браузере!" """,
}


def render(ctx):
    state = ctx.state
    lang = state.get("code_lang", "python")
    if lang not in EXAMPLES:
        lang = "python"
    code = state.get("code")
    if code is None or code == "":
        code = EXAMPLES[lang]
    output = state.get("code_output", "")

    options = "".join(
        f"<option value='{k}'{' selected' if k == lang else ''}>{v}</option>"
        for k, v in LANGS
    )
    lang_label = dict(LANGS).get(lang, "")
    if output:
        result_block = (
            "<div style='margin-top:1rem'>"
            "<label style='font-weight:600;font-size:.82rem;color:var(--text-muted);"
            "display:block;margin-bottom:.35rem'>Вывод:</label>"
            "<pre id='codeOutput' style='white-space:pre-wrap;word-break:break-word;"
            "background:#0a0a0f;border:1px solid var(--border);border-radius:10px;"
            "padding:1rem;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.85rem;"
            "line-height:1.55;max-height:380px;overflow:auto;color:#d7f5d3;'>"
            f"{esc(output)}</pre></div>"
        )
    else:
        result_block = ""

    return f"""
<style>
  .code-card {{
    background: var(--bg-card, #1e1e24);
    border: 1px solid var(--border, #2a2a30);
    border-radius: 16px;
    padding: 1.5rem;
    box-shadow: 0 4px 24px rgba(0,0,0,0.25), 0 1px 3px rgba(0,0,0,0.12);
    max-width: 960px;
  }}
  .code-card select, .code-card textarea {{
    border-radius: 10px; border: 1px solid var(--border, #2a2a30);
    background: var(--bg, #16161a); color: var(--text, #e8e8ec);
    padding: .6rem .85rem; font-size: .92rem; line-height: 1.5;
  }}
  .code-card textarea:focus, .code-card select:focus {{
    outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px rgba(106,174,255,.15);
  }}
  .lang-pills {{ display:flex; gap:.5rem; flex-wrap:wrap; margin-bottom:1rem; }}
  .lang-pill {{
    border:1px solid var(--border,#2a2a30); background:var(--bg,#16161a);
    color:var(--text-muted); border-radius:999px; padding:.35rem .8rem;
    font-size:.78rem; cursor:pointer; transition: all .15s;
  }}
  .lang-pill:hover {{ border-color: var(--accent); color: var(--text); }}
</style>

<div class="code-card">
  <h2 style="margin:0 0 .35rem; font-size:1.15rem; letter-spacing:-.01em;">🧪 Многоязычная песочница</h2>
  <p style="margin:0 0 1.1rem; color:var(--text-muted); font-size:.9rem; line-height:1.55;">
    Пиши и запускай код в браузере на разных языках. Pyodide выполняет только
    Python — поэтому JS, C++ и Ruby исполняются своими собственными рантаймами,
    каждый внутри вашего браузера, без сервера.
  </p>

  <form data-act="run-code" aria-label="Форма запуска кода">
    <label style="display:block;font-weight:600;font-size:.82rem;margin-bottom:.35rem;"
           for="code-lang">Язык:</label>
    <select id="code-lang" name="code-lang" style="max-width:100%;margin-bottom:1rem;">
      {options}
    </select>

    <label style="display:block;font-weight:600;font-size:.82rem;margin-bottom:.35rem;"
           for="codeArea">Код:</label>
    <textarea id="codeArea" name="code" spellcheck="false" style="width:100%;min-height:220px;resize:vertical;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.88rem;line-height:1.55;"
              placeholder="Введите код…">{esc(code)}</textarea>

    <div style="display:flex;gap:.6rem;align-items:center;margin-top:1rem;flex-wrap:wrap;">
      <button type="submit" class="btn btn-primary" aria-label="Запустить код">▶ Запустить</button>
      <span style="color:var(--text-muted);font-size:.78rem;">{lang_label}</span>
    </div>
  </form>

  <div id="codeResult">
    {result_block}
  </div>
  <p style="color:var(--text-muted);font-size:.78rem;line-height:1.5;margin-top:1rem;">
    ⚠️ Среда полностью клиентская: код выполняется в вашем браузере, ничего не
    отправляется на сервер. Python и JavaScript мгновенны; C++ подгружает
    лёгкий интерпретатор, а Ruby впервые качает свой рантайм из CDN
    (~20–30 МБ) — дальше из кеша браузера.
  </p>
</div>
"""
