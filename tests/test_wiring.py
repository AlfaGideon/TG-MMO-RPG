"""Целостность проекта: манифест, действия, импорты. python3 tests/test_wiring.py"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILED = []

LINE_LIMIT = 500          # предел длины модуля, см. .arena/CONTEXT.md


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


def main():
    html = open("index.html", encoding="utf-8").read()
    manifest = json.load(open("modules.json", encoding="utf-8"))

    print("\n— Манифест modules.json —")
    listed = manifest["modules"]
    on_disk = [p for d in ("engine", "webapp", "webapp/pages", "webapp/actions")
               for p in sorted(glob.glob(f"{d}/*.py"))
               if not p.endswith("__init__.py")]
    check(not [m for m in listed if not os.path.exists(m)],
          f"все {len(listed)} модулей манифеста существуют")
    check(not [p for p in on_disk if p not in listed],
          "нет .py-файлов вне манифеста")
    check(len(listed) == len(set(listed)), "в манифесте нет дублей")
    # Каталог каждого модуля должен объявляться пакетом, иначе импорт не найдёт его.
    pkgs = set(manifest["packages"])
    check(not [m for m in listed if os.path.dirname(m) not in pkgs],
          "каталог каждого модуля объявлен пакетом")

    print("\n— Аварийный список в index.html —")
    # FALLBACK обязан совпадать с modules.json: иначе при недоступном
    # modules.json страница молча грузит устаревший набор модулей.
    fb = re.search(r"const FALLBACK = \{(.*?)\n\};", html, re.S)
    check(fb is not None, "FALLBACK найден в index.html")
    if fb:
        fb_mods = re.findall(r'"([\w/]+\.py)"', fb.group(1))
        check(fb_mods == listed, "FALLBACK совпадает с modules.json по составу и порядку")
    check('fetch("modules.json' in html, "index.html читает modules.json")
    check("webapp/static/admin.css" in html, "подключён admin.css")
    check(html.count("<script") >= 1, "в index.html подключён script")

    print("\n— Импорты покрыты манифестом —")
    # Каждый внутренний импорт должен разрешаться в модуль из манифеста.
    # Именно этот разрыв ловит ошибку вида "cannot import name 'session'".
    known = set(listed)
    for src_path in listed:
        src = open(src_path, encoding="utf-8").read()
        for pkg, names in re.findall(r"^\s*from\s+(webapp|engine)\s+import\s+([^\n(]+)", src, re.M):
            for raw in names.split(","):
                name = raw.strip().split(" as ")[0].strip()
                cand = f"{pkg}/{name}.py"
                if os.path.exists(cand):
                    check(cand in known,
                          f"{src_path}: {pkg}.{name} есть в манифесте")

    print("\n— Порядок загрузки —")
    for dep, dependant in [("engine/data.py", "engine/world.py"),
                           ("engine/rules.py", "engine/itemui.py"),
                           ("engine/itemui.py", "engine/inventory.py"),
                           ("engine/itemui.py", "engine/shop.py"),
                           ("engine/items.py", "engine/craft.py"),
                           ("engine/items.py", "engine/auction.py"),
                           ("engine/craft.py", "engine/trade.py"),
                           ("engine/auction.py", "engine/trade.py"),
                           ("engine/craft.py", "engine/combat.py"),
                           ("engine/trade.py", "engine/game.py"),
                           ("engine/inventory.py", "engine/game.py"),
                           ("engine/shop.py", "engine/game.py"),
                           ("webapp/html.py", "webapp/dom.py"),
                           ("webapp/transport.py", "webapp/telegram.py"),
                           ("webapp/app.py", "webapp/boot.py")]:
        check(listed.index(dep) < listed.index(dependant), f"{dep} раньше {dependant}")

    print("\n— Страницы панели доступны из меню —")
    # Страница, которой нет в PAGES/NAV_SECTIONS, для пользователя не существует:
    # файл лежит в репозитории, а в панели раздела нет. Именно так «пропали»
    # возможности обновления 8, пока они жили только в серверном стеке.
    app_src = open("webapp/app.py", encoding="utf-8").read()
    page_files = {os.path.basename(f)[:-3] for f in glob.glob("webapp/pages/*.py")
                  if not f.endswith("__init__.py")}
    nav_block = re.search(r"NAV_SECTIONS = \[(.*?)\n\]", app_src, re.S)
    nav_keys = set(re.findall(r'"([\w]+)"', nav_block.group(1))) if nav_block else set()
    pages_block = re.search(r"PAGES = \[(.*?)\n\]", app_src, re.S)
    page_keys = set(re.findall(r'\("([\w]+)",', pages_block.group(1))) if pages_block else set()
    # dungeons рисуется внутри вкладки «Мир», своего пункта меню не имеет
    standalone = page_files - {"dungeons"}
    for mod in sorted(standalone):
        check(any(mod.startswith(k) or k in mod for k in page_keys),
              f"страница {mod} подключена в PAGES")
    for key in sorted(page_keys):
        check(key in nav_keys, f"раздел «{key}» виден в боковом меню")

    print("\n— Действия UI —")
    used = set()
    for f in glob.glob("webapp/pages/*.py"):
        used |= set(re.findall(r"data-act=['\"]([\w-]+)", open(f, encoding="utf-8").read()))
    registered = set()
    for f in glob.glob("webapp/actions/*.py") + ["webapp/app.py"]:
        src = open(f, encoding="utf-8").read()
        registered |= set(re.findall(r"""(?:A|dom\.register)\(\s*["']([\w-]+)["']""", src))
    check(not (used - registered), f"все {len(used)} data-act зарегистрированы")
    # nav и logout рисуются кодом навигации в app.py, а не страницами
    check(not (registered - used - {"nav", "logout"}), "нет лишних обработчиков")

    print("\n— Чистота движка —")
    for f in sorted(glob.glob("engine/*.py")):
        src = open(f, encoding="utf-8").read()
        bad = re.findall(r"^\s*(?:from|import)\s+(js|pyodide|webapp)\b", src, re.M)
        check(not bad, f"{f} не зависит от браузера/webapp")

    print("\n— Страницы без DOM-импортов —")
    for f in sorted(glob.glob("webapp/pages/*.py")):
        src = open(f, encoding="utf-8").read()
        check("webapp.dom" not in src, f"{f} рендерит чистый HTML")

    print("\n— Размер модулей —")
    # Лимит держит файлы читаемыми, но не заставляет дробить логику на
    # огрызки: 500 строк — предел, после которого модуль правда пора делить.
    big = []
    for f in on_disk + ["index.html"]:
        n = len(open(f, encoding="utf-8").read().splitlines())
        if n > LINE_LIMIT:
            big.append(f"{f}:{n}")
    check(not big, f"нет файлов длиннее {LINE_LIMIT} строк ({', '.join(big) or 'ок'})")

    print("\n" + "=" * 46)
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}")
        for f in FAILED:
            print("   -", f)
        return 1
    print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
