"""Целостность проекта: манифест, действия, импорты. python3 tests/test_wiring.py"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


def main():
    html = open("index.html", encoding="utf-8").read()

    print("\n— Манифест index.html —")
    listed = [m for m in re.findall(r'"([\w/]+\.py)"', html) if not m.startswith("/")]
    on_disk = [p for d in ("engine", "webapp", "webapp/pages", "webapp/actions")
               for p in sorted(glob.glob(f"{d}/*.py"))
               if not p.endswith("__init__.py")]
    check(not [m for m in listed if not os.path.exists(m)],
          f"все {len(listed)} модулей манифеста существуют")
    check(not [p for p in on_disk if p not in listed],
          "нет .py-файлов вне манифеста")
    check("webapp/static/admin.css" in html, "подключён admin.css")
    check(html.count("<script") >= 1, "в index.html подключён script")

    print("\n— Порядок загрузки —")
    for dep, dependant in [("engine/data.py", "engine/world.py"),
                           ("webapp/html.py", "webapp/dom.py"),
                           ("webapp/transport.py", "webapp/telegram.py"),
                           ("webapp/app.py", "webapp/boot.py")]:
        check(listed.index(dep) < listed.index(dependant), f"{dep} раньше {dependant}")

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
    big = []
    for f in on_disk + ["index.html"]:
        n = len(open(f, encoding="utf-8").read().splitlines())
        if n > 320:
            big.append(f"{f}:{n}")
    check(not big, f"нет файлов длиннее 320 строк ({', '.join(big) or 'ок'})")

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
