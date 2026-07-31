"""Собирает все Python-модули браузерного стека в один файл.

python3 tools/build_bundle.py

Зачем: index.html раньше тянул ~80 .py-файлов отдельными fetch-запросами
(они шли параллельно, но каждый — это TLS/HTTP-раунд-трип, и на плохой
мобильной сети именно это часто "тормозило" запуск панели сильнее самого
Pyodide). Здесь модули упаковываются в один JSON — webapp/bundle.json —
чтобы страница могла поднять весь код одним запросом. Если бандл не
собран или устарел — index.html сам откатывается на старый способ
(по одному файлу), так что бандл — это ускорение, а не точка отказа.

modules.json остаётся единственным источником правды о СОСТАВЕ и ПОРЯДКЕ
модулей (это же читает test_wiring.py). Бандл — лишь производный от него
артефакт; после правки любого модуля из manifest нужно перезапустить эту
команду (tests/test_wiring.py проверяет, что бандл не отстал).
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(ROOT, "modules.json")
BUNDLE_PATH = os.path.join(ROOT, "webapp", "bundle.json")


def build():
    manifest = json.load(open(MANIFEST_PATH, encoding="utf-8"))
    modules = manifest["modules"]
    files = {}
    for path in modules:
        with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
            files[path] = fh.read()
    digest = fingerprint(modules, files)
    bundle = {
        "_comment": "Сгенерировано tools/build_bundle.py — не редактировать руками.",
        "digest": digest,
        "packages": manifest.get("packages", []),
        "modules": modules,
        "files": files,
    }
    with open(BUNDLE_PATH, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, ensure_ascii=False, separators=(",", ":"))
    return bundle


def fingerprint(modules, files):
    """Хэш состава + содержимого — по нему проверяется актуальность бандла."""
    h = hashlib.sha256()
    for path in modules:
        h.update(path.encode("utf-8"))
        h.update(b"\0")
        h.update(files[path].encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def current_digest():
    """Хэш того, что лежит на диске СЕЙЧАС (без перезаписи бандла)."""
    manifest = json.load(open(MANIFEST_PATH, encoding="utf-8"))
    modules = manifest["modules"]
    files = {}
    for path in modules:
        with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
            files[path] = fh.read()
    return fingerprint(modules, files)


def bundle_digest():
    if not os.path.exists(BUNDLE_PATH):
        return None
    try:
        return json.load(open(BUNDLE_PATH, encoding="utf-8")).get("digest")
    except Exception:
        return None


def is_stale():
    return bundle_digest() != current_digest()


def main():
    bundle = build()
    print(f"✅ webapp/bundle.json собран: {len(bundle['files'])} модулей, "
          f"{sum(len(s) for s in bundle['files'].values())} символов, "
          f"digest {bundle['digest'][:12]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
