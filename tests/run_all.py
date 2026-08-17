"""Запуск всех проверок: python3 tests/run_all.py

Раньше список наборов был зашит вручную (SUITES = [...]), и новые наборы,
написанные в `tests/`, в прогон не попадали — так оказались забытыми 12
pytest-наборов (`test_karma_and_omens.py`, `test_lore_and_legends.py`,
`test_economy_and_lunar.py` и другие). Теперь наборы обнаруживаются сами:
берутся все `tests/test_*.py`, файлы с `import pytest` запускаются через
`python3 -m pytest -q`, остальные — как обычные скрипты. Забыть новый
набор больше нельзя.

Также расширена проверка зависимостей: раньше проверялись только
`sqlalchemy`/`aiosqlite`, а отсутствие `aiogram`/`fastapi`/`Pillow`
проявлялось как ImportError уже внутри наборов (и выглядело как честный
провал вместо «зависимости не установлены»).
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Без этих пакетов соответствующие сценарии не падают, а ТИХО ПРОПУСКАЮТСЯ
# (или падают ModuleNotFoundError уже внутри набора) — зелёный прогон тогда
# ничего не доказывает. Список покрывает оба стека и все виды наборов.
DEPS = {
    "sqlalchemy": "серверные БД-сценарии (core/)",
    "aiosqlite": "серверные БД-сценарии (core/)",
    "aiogram": "сценарии бота (bot/)",
    "fastapi": "сценарии админ-панели (admin/)",
    "PIL": "генерация и проверка изображений (пакет Pillow)",
    "jinja2": "шаблоны админ-панели",
    # Новые starlette тянут TestClient через httpx2, старые — через httpx:
    # достаточно любого из двух (разбор альтернатив — в tests/_deps.missing).
    "httpx|httpx2": "HTTP-транспорт (TestClient)",
    "aiohttp": "прокси-транспорт бота",
    "pytest": "pytest-наборы в tests/",
}

# Наборы в стиле pytest отличаем по импорту pytest в начале файла.
PYTEST_MARKER = re.compile(r"^\s*(?:import pytest|from pytest)", re.M)


def discover():
    """Все tests/test_*.py, отсортированные по имени (детерминизм)."""
    suites = []
    for name in sorted(os.listdir(HERE)):
        if name.startswith("test_") and name.endswith(".py"):
            suites.append(os.path.join(HERE, name))
    return suites


def check_deps():
    # Разбор альтернатив ("httpx|httpx2" — годится любой) вынесен в _deps,
    # чтобы у наборов и у раннера была одна и та же логика.
    sys.path.insert(0, HERE)
    from _deps import missing as absent

    missing = [f"{pkg} ({DEPS[pkg]})" for pkg in absent(*DEPS)]
    if missing:
        print("!" * 46)
        print("⚠️  ВНИМАНИЕ: не установлены зависимости:")
        for m in missing:
            print(f"    - {m}")
        print("⚠️  Часть наборов будет ПРОПУЩЕНА или упадёт с ImportError")
        print("⚠️  (это НЕ успех).")
        print("⚠️  Установи: pip install -r requirements.txt pytest pytest-asyncio")
        print("!" * 46)
    return missing


def run_one(path):
    """Запускает один набор подходящим раннером. Возвращает exit-код."""
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    if PYTEST_MARKER.search(src):
        return subprocess.call([sys.executable, "-m", "pytest", "-q", path])
    return subprocess.call([sys.executable, path])


def main():
    missing = check_deps()
    suites = discover()
    failed = []
    for path in suites:
        name = os.path.basename(path)
        print(f"\n{'=' * 46}\n▶ {name}\n{'=' * 46}")
        code = run_one(path)
        if code:
            failed.append(name)
    print(f"\n{'=' * 46}")
    if failed:
        print("❌ Провалены наборы: " + ", ".join(failed))
        return 1
    if missing:
        print("⚠️  Все доступные наборы зелёные, но часть сценариев "
              "пропущена из-за отсутствующих зависимостей!")
    print(f"✅ Все наборы пройдены ({len(suites)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
