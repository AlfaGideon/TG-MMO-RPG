"""Целостность webapp/bundle.json: он не должен отставать от файлов.

Запуск: python3 tests/test_bundle_integrity.py

Зачем. Браузерный стек грузит один склеенный файл `webapp/bundle.json`
(85 модулей). Если разработчик правит `engine/*.py` или `webapp/*.py` и
забывает `python3 tools/build_bundle.py`, панель на холодном старте берёт
старый код: тесты при этом зелёные (они импортируют файлы напрямую), а в
браузере поведение старое. `tests/test_wiring.py` сверяет manifest с
FALLBACK, но не проверяет содержимое бандла — этот набор закрывает дыру:

  1. bundle.json — валидный JSON с ожидаемыми ключами;
  2. состав modules бандла совпадает с modules.json (состав и порядок);
  3. содержимое каждого модуля в бандле байт-в-байт равно файлу на диске;
  4. в бандле нет модулей-призраков, которых нет в манифесте.
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

BUNDLE = os.path.join(ROOT, "webapp", "bundle.json")
MANIFEST = os.path.join(ROOT, "modules.json")

FAILED = []
REBUILD_HINT = "запусти: python3 tools/build_bundle.py и закоммить результат"


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main():
    print("\n— Бандл читается —")
    check(os.path.exists(BUNDLE), "webapp/bundle.json существует")
    if not os.path.exists(BUNDLE):
        return 1
    try:
        bundle = json.load(open(BUNDLE, encoding="utf-8"))
        ok_json = True
    except json.JSONDecodeError as e:
        ok_json = False
        print(f"     JSON битый: {e}")
    check(ok_json, "webapp/bundle.json — валидный JSON")
    if not ok_json:
        return 1

    for key in ("packages", "modules", "files", "digest"):
        check(key in bundle, f"в бандле есть ключ «{key}»")

    manifest = json.load(open(MANIFEST, encoding="utf-8"))
    listed = list(manifest["modules"])
    bundled = list(bundle.get("modules") or [])

    print("\n— Состав совпадает с modules.json —")
    check(bundled == listed,
          "порядок и состав модулей идентичны manifest'у"
          + ("" if bundled == listed else f" — {REBUILD_HINT}"))
    missing = [m for m in listed if m not in bundled]
    check(not missing,
          "в бандле нет пропущенных модулей"
          + (f" — нет {missing}; {REBUILD_HINT}" if missing else ""))
    ghosts = [m for m in bundled if m not in listed]
    check(not ghosts,
          "в бандле нет модулей-призраков"
          + (f" — лишние {ghosts}" if ghosts else ""))

    print("\n— Содержимое бандла совпадает с файлами на диске —")
    files = bundle.get("files") or {}
    stale = []
    absent = []
    for path in listed:
        disk_path = os.path.join(ROOT, path)
        if not os.path.exists(disk_path):
            absent.append(path)
            continue
        if path not in files:
            stale.append(path)
            continue
        on_disk = open(disk_path, encoding="utf-8").read()
        if sha(files[path]) != sha(on_disk):
            stale.append(path)
    check(not absent, "каждый модуль манифеста лежит на диске"
                      + (f" — нет {absent}" if absent else ""))
    check(not stale,
          f"содержимое всех {len(listed)} модулей актуально"
          + (f" — устарели {stale}; {REBUILD_HINT}" if stale else ""))

    print("\n" + "=" * 46)
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}:")
        for f in FAILED:
            print("   -", f)
        return 1
    print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
