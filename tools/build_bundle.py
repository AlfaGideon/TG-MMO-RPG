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
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(ROOT, "modules.json")
BUNDLE_PATH = os.path.join(ROOT, "webapp", "bundle.json")
INDEX_PATH = os.path.join(ROOT, "index.html")

# Статика, чьи ?v= нужно авто-бампать при сборке. GitHub Pages кеширует
# файлы агрессивно: если версия в href зашита вручную, правки CSS/JS не
# видны, пока не обновишь цифру руками — частый источник жалоб
# «дизайн не меняется». Теперь версия = хэш содержимого файла.
STATIC_ASSETS = [
    ("webapp/static/admin.css", "admin.css?v="),
    ("webapp/static/interactions.js", "interactions.js?v="),
]


def _asset_hash(rel):
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        return None
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:12]


def stamp_static_versions():
    """Подставляет актуальные ?v= для CSS/JS в index.html.

    Меняет index.html только если версия действительно устарела, поэтому
    повторные сборки без правки статики не создают шума в git.
    """
    if not os.path.exists(INDEX_PATH):
        return 0
    text = open(INDEX_PATH, encoding="utf-8").read()
    changed = 0
    for rel, marker in STATIC_ASSETS:
        h = _asset_hash(rel)
        if h is None:
            continue
        new = re.sub(re.escape(marker) + r"[A-Za-z0-9]+", marker + h, text)
        if new != text:
            text = new
            changed += 1
    if changed:
        with open(INDEX_PATH, "w", encoding="utf-8") as fh:
            fh.write(text)
    return changed


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
    bumped = stamp_static_versions()
    print(f"✅ webapp/bundle.json собран: {len(bundle['files'])} модулей, "
          f"{sum(len(s) for s in bundle['files'].values())} символов, "
          f"digest {bundle['digest'][:12]}…")
    if bumped:
        print(f"   + обновлены ?v= для {bumped} статических файлов (анти-кеш CSS/JS)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
