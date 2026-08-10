#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Статическая проверка Jinja2-шаблонов админ-панели.

Ловит классы ошибок, которые валят страницы панели в рантайме
(500 при открытии страницы), и объясняет причину до запуска сервера:

1. Синтаксические ошибки шаблона — jinja2 не сможет его скомпилировать.
2. Вызовы встроенных функций Python (set(), list(), len(), min()...),
   которых НЕТ в окружении Jinja2. Шаблонам доступны только глобалы
   Jinja2 (range, dict, namespace, cycler, joiner, lipsum) и переменные,
   переданные в контекст из view. Поэтому `{{ len(x) }}` падает с
   UndefinedError: 'len' is undefined — вместо этого нужен фильтр
   `{{ x|length }}`. Реальный пример: `connected_dirs.get(loc.id, set())`
   ронял редактор мира — в шаблоне нет встроенной функции `set`.
3. Ссылки на отсутствующие шаблоны ({% extends %}, {% import %}) —
   упадут при рендере первой же страницы.

Запуск:  python tools/check_templates.py
Возврат: 0 — всё чисто; 1 — найдены проблемы; 2 — нечем проверять
         (не установлен jinja2).
"""
import builtins
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL_DIR = os.path.join(ROOT, "admin", "templates")

try:
    from jinja2 import Environment, FileSystemLoader, nodes
except ImportError:
    print(
        "❌ jinja2 не установлен — проверка шаблонов невозможна.\n"
        "   Установи зависимости: pip install -r requirements.txt"
    )
    sys.exit(2)

env = Environment(loader=FileSystemLoader(TPL_DIR))

# Встроенные функции Python, которых нет среди глобалов Jinja2.
# Именно их вызов из шаблона падает в рантайме с UndefinedError.
BLACKLIST = (
    set(n for n in dir(builtins) if not n.startswith("_")) - set(env.globals)
)
# «Тяжёлые» имена, которые вряд ли окажутся переменными контекста —
# выводим для них подсказку с заменой.
HINTS = {
    "set": "используй список `[]` или передай пустое множество из view",
    "list": "используй список `[]` или фильтр `|list`",
    "tuple": "используй кортеж из view или список `[]`",
    "len": "используй фильтр `|length`",
    "min": "используй фильтр `|min`",
    "max": "используй фильтр `|max`",
    "sum": "используй фильтр `|sum`",
    "abs": "используй фильтр `|abs`",
    "round": "используй фильтр `|round`",
    "int": "используй фильтр `|int`",
    "float": "используй фильтр `|float`",
    "str": "используй фильтр `|string`",
    "bool": "передай значение из view",
    "dict": "это глобал Jinja2, но проверь опечатку",
    "range": "это глобал Jinja2, но проверь опечатку",
    "zip": "собери данные в view",
    "enumerate": "собери данные в view",
    "sorted": "сортируй в view или фильтром `|sort`",
    "reversed": "используй фильтр `|reverse`",
    "print": "вывод в консоль из шаблона недоступен",
    "open": "работа с файлами в шаблоне недоступна",
    "getattr": "обращайся к атрибуту через точку: obj.attr",
    "hasattr": "проверяй наличие атрибута в view",
    "isinstance": "проверяй тип в view",
}


def collect_known_names(tpl_node):
    """Имена, определённые внутри шаблона: set/макросы/циклы/импорты."""
    known = set()

    def add_target(target):
        if isinstance(target, nodes.Tuple):
            for item in target.items:
                if isinstance(item, nodes.Name):
                    known.add(item.name)
        elif isinstance(target, nodes.Name):
            known.add(target.name)

    for node in tpl_node.find_all(nodes.Assign):
        add_target(node.target)
    for node in tpl_node.find_all(nodes.For):
        add_target(node.target)
    for node in tpl_node.find_all(nodes.Macro):
        known.add(node.name)
    for node in tpl_node.find_all(nodes.Block):
        known.add(node.name)
    for node in tpl_node.find_all(nodes.Import):
        known.add(node.target)
    for node in tpl_node.find_all(nodes.FromImport):
        for name, alias in node.names:
            known.add(alias or name)
    return known


def referenced_templates(tpl_node):
    """Имена шаблонов, на которые ссылается текущий (extends/import)."""
    out = set()
    for node in tpl_node.find_all(nodes.Extends):
        if isinstance(node.template, nodes.Const):
            out.add(node.template.value)
    for node in tpl_node.find_all(nodes.Import):
        if isinstance(node.template, nodes.Const):
            out.add(node.template.value)
    for node in tpl_node.find_all(nodes.FromImport):
        if isinstance(node.template, nodes.Const):
            out.add(node.template.value)
    return out


def check_template(path):
    """Возвращает список проблем для одного файла."""
    problems = []
    with open(path, encoding="utf-8") as f:
        src = f.read()

    try:
        tpl = env.parse(src)
    except Exception as exc:  # TemplateSyntaxError и пр.
        problems.append(f"{path}: синтаксическая ошибка: {exc}")
        return problems

    known = collect_known_names(tpl)

    for call in tpl.find_all(nodes.Call):
        callee = call.node
        if not isinstance(callee, nodes.Name):
            continue
        name = callee.name
        if name in BLACKLIST and name not in known:
            hint = HINTS.get(name)
            suffix = f" — {hint}" if hint else ""
            problems.append(
                f"{path}:{call.lineno}: вызов недоступной функции "
                f"'{name}()'. В шаблонах Jinja2 нет встроенных функций "
                f"Python{suffix}."
            )

    for ref in sorted(referenced_templates(tpl)):
        try:
            env.loader.get_source(env, ref)
        except Exception:
            problems.append(
                f"{path}: ссылка на отсутствующий шаблон '{ref}' "
                f"({nodes.Extends.__name__}/import)."
            )

    return problems


def main():
    if not os.path.isdir(TPL_DIR):
        print(f"❌ Папка шаблонов не найдена: {TPL_DIR}")
        return 1

    files = sorted(
        os.path.join(TPL_DIR, n)
        for n in os.listdir(TPL_DIR)
        if n.endswith(".html")
    )
    if not files:
        print("❌ В папке шаблонов нет .html файлов.")
        return 1

    problems = []
    for path in files:
        problems.extend(check_template(path))

    print(f"🧪 Проверено шаблонов: {len(files)}")
    if problems:
        print(f"❌ Найдено проблем: {len(problems)}\n")
        for p in problems:
            print(f"   {p}")
        print(
            "\nИсправь ошибки выше и запусти сервер заново — панель не "
            "поднимется, пока шаблоны не пройдут проверку."
        )
        return 1

    print("✅ Все шаблоны валидны: синтаксис, импорты и вызовы функций в порядке.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
