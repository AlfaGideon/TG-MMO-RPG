"""DevOps-действия: импорт/экспорт JSON с diff-preview и SQL-песочница."""
import json
import re

from webapp import dom


SOURCE_KEYS = {
    "players": lambda s: [{"tg_id": k, **vars(p)} for k, p in s.players.items()],
    "world": lambda s: [{"key": k, **vars(c)} for k, c in s.world.items()],
    "settings": lambda s: [{"key": k, "value": v} for k, v in s.settings.items()],
}


def register(app, A):
    A("data-export-file", lambda _="": _export_file(app))
    A("data-import-preview", lambda _="": _import_preview(app))
    A("data-import-apply", lambda _="": _import_apply(app))
    A("data-sql-run", lambda _="": _sql_run(app))


def _export_file(app):
    """Скачать текущее состояние как .json-файл."""
    from js import document
    raw = app.store.backend.get("shadowlands") or "{}"
    blob = __import__("js").Blob.new([raw], {"type": "application/json"})
    url = __import__("js").URL.createObjectURL(blob)
    a = document.createElement("a")
    a.href = url
    a.download = "shadowlands_export.json"
    a.click()
    __import__("js").URL.revokeObjectURL(url)
    dom.toast("Файл экспорта скачан")


def _import_preview(app):
    raw = dom.value("#ioBox").strip()
    if not raw:
        dom.toast("Вставь JSON для импорта", "err")
        return
    try:
        incoming = json.loads(raw)
    except Exception as e:
        dom.toast(f"Невалидный JSON: {e}", "err")
        return
    current = _snapshot(app.store)
    diff = _diff(current, incoming)
    dom.html("#diffBox", _diff_html(diff))
    dom.toast(f"Добавлено: {len(diff['added'])}, изменено: {len(diff['changed'])}, удалено: {len(diff['removed'])}")


def _import_apply(app):
    raw = dom.value("#ioBox").strip()
    if not raw:
        dom.toast("Нечего применять", "err")
        return
    from js import window
    if not window.confirm("Применить импорт? Текущие данные будут перезаписаны. Сделай экспорт на всякий случай."):
        return
    try:
        json.loads(raw)
    except Exception as e:
        dom.toast(f"Невалидный JSON: {e}", "err")
        return
    app.store.backend.set("shadowlands", raw)
    app.store.load()
    app.bot.game.world = app.store.world
    app.bot.transport.settings = app.store.settings
    dom.html("#diffBox", "")
    dom.toast("Импорт применён")
    app.render()


def _sql_run(app):
    query = dom.value("#sqlQuery").strip()
    if not query:
        dom.toast("Введи запрос", "err")
        return
    try:
        cols, rows = _run_query(app.store, query)
        dom.html("#sqlResult", _sql_html(cols, rows))
        dom.toast(f"Найдено строк: {len(rows)}")
    except Exception as e:
        dom.html("#sqlResult", f"<div class='hint err'>Ошибка: {esc(str(e))}</div>")
        dom.toast(str(e)[:80], "err")


def _snapshot(store):
    return {
        "players": {str(k): p.to_dict() for k, p in store.players.items()},
        "world": {k: _cell_dict(c) for k, c in store.world.items()},
        "settings": dict(store.settings),
    }


def _cell_dict(c):
    from engine.storage import _cell_dict as cd
    return cd(c)


def _diff(current, incoming):
    added, changed, removed = [], [], []
    for section in ("players", "world", "settings"):
        cur = current.get(section, {})
        inc = incoming.get(section, {})
        for k, v in inc.items():
            if k not in cur:
                added.append((section, k, v))
            elif cur[k] != v:
                changed.append((section, k, cur[k], v))
        for k in cur:
            if k not in inc:
                removed.append((section, k, cur[k]))
    return {"added": added, "changed": changed, "removed": removed}


def _diff_html(diff):
    from webapp.html import esc
    lines = []
    if not any(diff.values()):
        return "<div class='hint'>Нет изменений — импорт идентичен текущему состоянию.</div>"
    for section, key, val in diff["added"]:
        lines.append(f"<div class='diff-row add'><b>+ {section}/{esc(str(key))}</b> "
                     f"<span class='muted'>{esc(json.dumps(val, ensure_ascii=False)[:120])}</span></div>")
    for section, key, old, new in diff["changed"]:
        lines.append(f"<div class='diff-row change'><b>~ {section}/{esc(str(key))}</b> "
                     f"<span class='muted'>{esc(json.dumps(old, ensure_ascii=False)[:60])}</span> "
                     f"→ <span>{esc(json.dumps(new, ensure_ascii=False)[:60])}</span></div>")
    for section, key, val in diff["removed"]:
        lines.append(f"<div class='diff-row remove'><b>− {section}/{esc(str(key))}</b> "
                     f"<span class='muted'>{esc(json.dumps(val, ensure_ascii=False)[:120])}</span></div>")
    return "\n".join(lines)


def _run_query(store, query):
    query = re.sub(r"\s+", " ", query.strip())
    m = re.match(r"SELECT\s+(.*?)\s+FROM\s+(\w+)\s*(?:WHERE\s+(.+))?", query, re.IGNORECASE)
    if not m:
        raise ValueError("Поддерживаются только запросы: SELECT ... FROM ... [WHERE ...]")
    cols_part, table, where = m.groups()
    if table not in SOURCE_KEYS:
        raise ValueError(f"Доступные таблицы: {', '.join(SOURCE_KEYS)}")
    rows = SOURCE_KEYS[table](store)
    if where:
        expr = _safe_expr(where)
        rows = [r for r in rows if _eval_expr(expr, r)]
    if cols_part.strip() == "*":
        if not rows:
            return [], []
        cols = list(rows[0].keys())
    else:
        cols = [c.strip() for c in cols_part.split(",")]
    return cols, [[r.get(c) for c in cols] for r in rows]


def _safe_expr(where):
    allowed = re.compile(r"^[a-zA-Z0-9_\s\+\-\*\/\%\<\>\=\!\.\"\'\(\),\[\]]+$")
    if not allowed.match(where):
        raise ValueError("Запрос содержит недопустимые символы")
    return where


def _eval_expr(expr, row):
    """Безопасный вычислитель WHERE-выражений — без eval().

    `eval` с `{"__builtins__": {}}` песочницей не является: выражения
    вида `().__class__.__bases__[0].__subclasses__()` (а все символы этой
    конструкции фильтр `_safe_expr` пропускал) дают произвольный код прямо
    в рантайме панели. Здесь вместо eval — разбор через ast и белый список
    узлов: поля строки, литералы, арифметика, сравнения, and/or/not, in
    и единственный разрешённый вызов get("поле").
    """
    import ast

    def get(path, default=None):
        val = row
        for part in str(path).split("."):
            if isinstance(val, dict) and part in val:
                val = val[part]
            else:
                return default
        return val

    binops = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
              ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b,
              ast.Mod: lambda a, b: a % b}
    cmps = {ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b,
            ast.Lt: lambda a, b: a < b, ast.LtE: lambda a, b: a <= b,
            ast.Gt: lambda a, b: a > b, ast.GtE: lambda a, b: a >= b,
            ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b}

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float, str, bool, type(None))):
                return node.value
            raise ValueError(f"Литерал недопустим: {node.value!r}")
        if isinstance(node, ast.Name):
            if node.id in row:
                return row[node.id]
            raise ValueError(f"Неизвестное поле: {node.id}")
        if isinstance(node, ast.BinOp) and type(node.op) in binops:
            return binops[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not ev(node.operand)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -ev(node.operand)
        if isinstance(node, ast.BoolOp):
            vals = [ev(v) for v in node.values]
            if isinstance(node.op, ast.And):
                return all(vals)
            return any(vals)
        if isinstance(node, ast.Compare):
            left = ev(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                if type(op) not in cmps:
                    raise ValueError("Оператор запрещён")
                right = ev(comparator)
                if not cmps[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, (ast.List, ast.Tuple)):
            return [ev(e) for e in node.elts]
        if isinstance(node, ast.Call):
            if (isinstance(node.func, ast.Name) and node.func.id == "get"
                    and len(node.args) == 1 and not node.keywords):
                path = ev(node.args[0])
                if not isinstance(path, str):
                    raise ValueError("get() ждёт имя поля строкой")
                return get(path)
            raise ValueError("Вызовы функций запрещены (разрешён только get)")
        raise ValueError("Конструкция недопустима в фильтре")

    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Не разобрать выражение: {e}") from None
    return bool(ev(tree))


def _sql_html(cols, rows):
    from webapp.html import esc
    if not cols:
        return "<div class='hint'>Нет данных</div>"
    th = "".join(f"<th>{esc(str(c))}</th>" for c in cols)
    trs = ""
    for r in rows:
        trs += "<tr>" + "".join(f"<td>{esc(str(v))}</td>" for v in r) + "</tr>"
    return f"<div class='scroll'><table><tr>{th}</tr>{trs}</table></div>"


def esc(s):
    from webapp.html import esc as _esc
    return _esc(s)
