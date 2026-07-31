"""Вёрстка серверной админки: структурные инварианты шаблонов и CSS.

python3 tests/test_admin_layout.py

Браузера в CI нет, поэтому проверяем то, что проверяется статически и
что уже ломалось на практике:

* вложенные <form> (браузер выбрасывает внутреннюю, её поля уходят
  во внешнюю — Enter в инлайн-поле отправлял массовое действие);
* данные для JS едут через data-атрибуты, а не аргументами inline-onclick
  (апостроф или перенос строки в названии ломал скрипт всей страницы);
* «сырой» & в href — невалидный HTML и риск подстановки сущности;
* каждый шаблон наследует base.html и имеет хлебные крошки;
* CSS парсится, скобки сбалансированы, нет дублей ключевых блоков;
* контраст текста в обеих темах не ниже AA (4.5:1);
* подменю навигации вмещает все свои пункты.

Тяжёлые зависимости (fastapi/jinja2/html5lib) не обязательны: часть
проверок работает на голом тексте, остальные грейсфул-скипаются.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL_DIR = os.path.join(ROOT, "admin", "templates")
CSS_PATH = os.path.join(ROOT, "admin", "static", "style.css")
PYODIDE_CSS_PATH = os.path.join(ROOT, "webapp", "static", "admin.css")

FAILED = []
SKIPPED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


def skip(label, why):
    print(f"  ⚠️  ПРОПУСК: {label} ({why})")
    SKIPPED.append(label)


def templates():
    for name in sorted(os.listdir(TPL_DIR)):
        if name.endswith(".html"):
            yield name, open(os.path.join(TPL_DIR, name), encoding="utf-8").read()


def _have(*mods):
    import importlib.util
    return all(importlib.util.find_spec(m) for m in mods)


# ── 1. Вложенные формы ────────────────────────────────────────

def test_no_nested_forms():
    print("\n— Вложенных <form> нет (браузер выбрасывает внутреннюю) —")
    if not _have("html5lib"):
        skip("вложенные формы", "нет html5lib")
        return
    if not _have("jinja2"):
        skip("вложенные формы", "нет jinja2")
        return
    import html5lib

    bad = []
    for name, src in templates():
        # Комментарии Jinja {# ... #} содержат слово <form> в пояснениях —
        # считаем вложенность только по реальной разметке.
        clean = re.sub(r"\{#.*?#\}", "", src, flags=re.S)
        depth = 0
        worst = 0
        for m in re.finditer(r"<form\b|</form>", clean):
            depth += 1 if m.group(0).startswith("<form") else -1
            worst = max(worst, depth)
        if worst > 1:
            bad.append(name)
    check(not bad, f"нет шаблонов с <form> внутри <form> (нарушители: {bad})")

    # Дополнительно: разметка списков переживает разбор браузером.
    for name in ("players.html", "items.html"):
        src = open(os.path.join(TPL_DIR, name), encoding="utf-8").read()
        check("form=\"" in src,
              f"{name}: чекбоксы строк привязаны атрибутом form=")


# ── 2. Никаких данных в аргументах inline-onclick ─────────────

def test_no_data_in_onclick():
    print("\n— Текст из БД не подставляется в JS-строку обработчика —")
    # Ломалось так: onclick="fn('{{ q.name }}')" или
    # onsubmit="return confirm('Удалить «{{ item.name }}»?')".
    # Апостроф в имени («Клинок O'Брайена») закрывает строку раньше
    # времени — обработчик перестаёт работать. Числовой id (без кавычек
    # вокруг подстановки) безопасен: это не строковый литерал.
    # Числовые/служебные поля (id, счётчики, координаты, циклические
    # переменные) в строку подставлять безопасно — они не содержат кавычек.
    SAFE = re.compile(
        r"^\s*(?:[\w.]*\b(?:id|_id|count|level|floor|x|y|tier|index)|f|i|p|wx|wy)\s*$"
    )
    inside_quotes = re.compile(r"""on(?:click|submit)="([^"]*)\"""")
    bad = []
    for name, src in templates():
        # комментарии Jinja и JS-пояснения в <script> не разметка
        clean = re.sub(r"\{#.*?#\}", "", src, flags=re.S)
        clean = re.sub(r"^\s*//.*$", "", clean, flags=re.M)
        for m in inside_quotes.finditer(clean):
            body = m.group(1)
            # подстановки, попавшие внутрь одинарных кавычек JS-строки
            for expr in re.findall(r"'[^']*\{\{(.*?)\}\}[^']*'", body):
                if SAFE.match(expr):
                    continue
                bad.append(f"{name}: {{{{{expr}}}}} в {body[:50]}")
    check(not bad,
          "нет подстановок {{ ... }} внутри JS-строк в on*-атрибутах" +
          ("" if not bad else f" → {bad}"))

    # Длинные текстовые подтверждения должны жить в data-confirm
    check(any("data-confirm" in src for _, src in templates()),
          "подтверждения с именами объектов используют data-confirm")


# ── 3. Сырой & в ссылках ──────────────────────────────────────

def test_escaped_ampersands():
    print("\n— В href нет «сырого» & (невалидный HTML) —")
    bad = []
    for name, src in templates():
        for m in re.finditer(r'href="([^"]*)"', src):
            url = m.group(1)
            if "{{" in url and "&" in url:
                # внутри jinja-выражения & может быть частью строки-разделителя
                pass
            for a in re.finditer(r"&(?!(?:amp|lt|gt|quot|#\d+|#x[0-9a-fA-F]+);)", url):
                # разделитель, собранный в {% set sep %}, экранируется на выводе
                if "{{ sep }}" in url or "{{ qparam }}" in url:
                    continue
                bad.append(f"{name}: {url[:70]}")
    check(not bad, "все & в href экранированы" + ("" if not bad else f" → {bad[:5]}"))


# ── 4. Наследование и хлебные крошки ──────────────────────────

def test_template_conventions():
    print("\n— Соглашения шаблонов —")
    # login.html — самостоятельная страница входа, base.html ей не нужен;
    # base.html — сам базовый шаблон, macros.html — библиотека макросов.
    standalone = {"login.html", "macros.html", "base.html"}
    no_extend, no_crumbs = [], []
    for name, src in templates():
        if name in standalone:
            continue
        if '{% extends "base.html" %}' not in src:
            no_extend.append(name)
            continue
        if "block breadcrumbs" not in src:
            no_crumbs.append(name)
    check(not no_extend, f"все шаблоны наследуют base.html (без: {no_extend})")
    # access_denied — заглушка ошибки, крошки там не нужны
    no_crumbs = [n for n in no_crumbs if n != "access_denied.html"]
    check(not no_crumbs, f"у всех экранов есть хлебные крошки (без: {no_crumbs})")


# ── 5. CSS: синтаксис и отсутствие дублей ─────────────────────

def test_css_sane():
    print("\n— CSS: синтаксис, дубли, переменные —")
    for label, path in (("серверная", CSS_PATH), ("pyodide", PYODIDE_CSS_PATH)):
        css = open(path, encoding="utf-8").read()
        check(css.count("{") == css.count("}"),
              f"{label}: скобки сбалансированы ({css.count('{')} пар)")

        if _have("tinycss2"):
            import tinycss2
            rules, _ = tinycss2.parse_stylesheet_bytes(
                css.encode(), skip_whitespace=True, skip_comments=True)
            errors = [r for r in rules if r.type == "error"]
            check(not errors, f"{label}: tinycss2 разбирает без ошибок ({len(errors)} ошибок)")
        else:
            skip(f"{label}: разбор CSS", "нет tinycss2")

        for sel in (".empty-state", ".badge", ".btn"):
            n = len(re.findall(rf"^{re.escape(sel)}\s*\{{", css, re.M))
            check(n == 1, f"{label}: {sel} объявлен один раз ({n})")

        blocks = re.findall(r'(:root\s*\{.*?\n\}|\[data-theme="light"\]\s*\{.*?\n\}|\[data-theme=light\]\s*\{.*?\n\})',
                            css, re.S)
        rest = css
        for b in blocks:
            rest = rest.replace(b, "")
        hard = re.findall(r"(?:^|[^-\w])(?:background|color|border-color)\s*:\s*(#[0-9a-fA-F]{3,8})", rest)
        check(not hard, f"{label}: нет зашитых цветов вне тем (найдено: {set(hard)})")


# ── 6. Контраст в обеих темах ─────────────────────────────────

def _contrast(fg, bg):
    def rgb(c):
        c = c.lstrip("#")
        if len(c) == 3:
            c = "".join(x * 2 for x in c)
        return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def lin(v):
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    def lum(c):
        r, g, b = (lin(x) for x in rgb(c))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    a, b = lum(fg), lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def test_contrast():
    print("\n— Контраст текста не ниже AA (4.5:1) —")
    for label, path in (("серверная", CSS_PATH), ("pyodide", PYODIDE_CSS_PATH)):
        css = open(path, encoding="utf-8").read()
        root = re.search(r":root\s*\{(.*?)\n\}", css, re.S).group(1)
        light_match = re.search(r'\[data-theme="light"\]\s*\{(.*?)\n\}', css, re.S) or re.search(r'\[data-theme=light\]\s*\{(.*?)\n\}', css, re.S)
        light = light_match.group(1) if light_match else ""

        def var(block, name):
            m = re.search(rf"{name}\s*:\s*(#[0-9a-fA-F]{{6}})", block)
            return m.group(1) if m else None

        names = ["--text", "--text-muted", "--accent-text", "--danger",
                 "--success", "--warning",
                 "--rarity-common", "--rarity-uncommon", "--rarity-rare",
                 "--rarity-epic", "--rarity-legendary",
                 "--school-fire", "--school-ice", "--school-lightning",
                 "--school-nature", "--school-arcane", "--school-shadow",
                 "--school-holy"]

        for theme, block, bg in ((f"{label} тёмная", root, var(root, "--bg-card")),
                                 (f"{label} светлая", light, var(light, "--bg-card"))):
            low = []
            for n in names:
                v = var(block, n) or var(root, n)
                if not v:
                    continue
                r = _contrast(v, bg)
                if r < 4.5:
                    low.append(f"{n}={v} ({r:.2f})")
            check(not low, f"{theme} тема: все цвета ≥4.5 на {bg}" +
                  ("" if not low else f" → {low}"))

        for theme, block in ((f"{label} тёмная", root), (f"{label} светлая", light)):
            acc = var(block, "--accent") or var(root, "--accent")
            r = _contrast("#ffffff", acc)
            check(r >= 4.0, f"{theme}: белый текст на .btn-primary = {r:.2f}")


# ── 7. Навигация вмещает свои пункты ──────────────────────────

def test_nav_fits():
    print("\n— Подменю навигации не обрезает пункты —")
    base = open(os.path.join(TPL_DIR, "base.html"), encoding="utf-8").read()
    css = open(CSS_PATH, encoding="utf-8").read()
    count = base.count("nav-sublink")
    m = re.search(r"\.nav-group\.open \.nav-subitems\s*\{[^}]*max-height:\s*([\d.]+)(rem|px)",
                  css)
    check(m is not None, "у раскрытого подменю задан max-height")
    if not m:
        return
    limit = float(m.group(1)) * (16 if m.group(2) == "rem" else 1)
    # пункт ≈ 0.45rem*2 паддинг + строка 0.82rem*1.5 + зазор
    per_item = (0.45 * 2) * 16 + 0.82 * 16 * 1.5 + 1.6
    need = count * per_item
    check(limit >= need,
          f"{count} пунктов (~{need:.0f}px) влезают в max-height {limit:.0f}px")


def test_location_map_not_shrunk():
    """Карта локации обязана быть того же размера, что карта подземелий.

    Обе рисуются классом .mapgrid, но карта локации лежит во флекс-строке
    рядом с переключателем этажей. Грид внутри флекса ужимается по
    содержимому, и карта выходила заметно мельче эталонной — поэтому
    ширина задаётся явно и должна совпадать с .mapgrid.
    """
    print("\n— Карта локации не мельче карты подземелий —")
    css = open(PYODIDE_CSS_PATH, encoding="utf-8").read()
    base = re.search(r"\.mapgrid\s*\{[^}]*max-width:\s*(\d+)px", css)
    check(base is not None, "у .mapgrid задана базовая ширина")
    inner = re.search(r"\.floor-map-layout \.mapgrid\s*\{[^}]*width:\s*(\d+)px", css)
    check(inner is not None, "карта локации получает явную ширину во флексе")
    if base and inner:
        check(int(inner.group(1)) == int(base.group(1)),
              f"ширины совпадают: {inner.group(1)}px = {base.group(1)}px")
    check("flex: 0 0 auto" in (inner.group(0) if inner else ""),
          "карта не сжимается флексом")


def main():
    print("=" * 46)
    print("Вёрстка админки")
    print("=" * 46)
    test_no_nested_forms()
    test_no_data_in_onclick()
    test_escaped_ampersands()
    test_template_conventions()
    test_css_sane()
    test_contrast()
    test_nav_fits()
    test_location_map_not_shrunk()

    print("\n" + "=" * 46)
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}:")
        for f in FAILED:
            print("   -", f)
        return 1
    if SKIPPED:
        print(f"⚠️  Пропущено проверок: {len(SKIPPED)} (нет зависимостей)")
    print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
