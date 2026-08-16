"""Грейсфул-скип скриптовых наборов без необязательных зависимостей.

Проблема (пункт № 4 из IDEAS-100.md): скриптовые наборы (те, что запускаются
как `python3 tests/test_x.py`, а не через pytest) импортировали `bot/` или
`admin/` на верхнем уровне. На машине без `aiogram`/`fastapi` они падали
`ModuleNotFoundError` — прогон печатал «❌ Провалены наборы», хотя кода никто
не ломал. Серверные наборы уже умели скип (`except ImportError: sys.exit(0)`),
но каждый по-своему.

Здесь единая точка: набор в самом начале вызывает

    from _deps import require
    require("aiogram", "sqlalchemy")

Если пакета нет — печатается «⚠ Пропуск: …» и процесс завершается кодом 0
(run_all.py считает набор пройденным-с-предупреждением; общий баннер о
недостающих зависимостях он печатает сам).

Скип разрешён ТОЛЬКО по отсутствию пакета. Ошибки внутри самого набора
(AssertionError, TypeError и т. п.) сюда не попадают и остаются провалами.
"""
import importlib
import sys

# Человеческие названия — чтобы в выводе было понятно, что именно пропало.
WHY = {
    "aiogram": "сценарии бота",
    "fastapi": "сценарии админ-панели",
    "sqlalchemy": "серверные БД-сценарии",
    "aiosqlite": "серверные БД-сценарии",
    "PIL": "генерация изображений (пакет Pillow)",
    "jinja2": "шаблоны админ-панели",
    "httpx|httpx2": "HTTP-транспорт (TestClient)",
    "aiohttp": "прокси-транспорт бота",
}


def _have(name):
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False


def missing(*modules):
    """Список отсутствующих пакетов из перечисленных.

    Имя вида "httpx|httpx2" означает «подойдёт любой из двух»: новые
    версии starlette тянут TestClient через httpx2, старые — через httpx.
    """
    out = []
    for name in modules:
        if not any(_have(alt) for alt in name.split("|")):
            out.append(name)
    return out


def require(*modules):
    """Пропустить набор (exit 0), если хоть одного пакета нет."""
    absent = missing(*modules)
    if not absent:
        return
    parts = [f"{n} ({WHY.get(n, 'необязательная зависимость')})" for n in absent]
    print("⚠ Пропуск: не установлены " + ", ".join(parts))
    print("  Установка: pip install -r requirements.txt")
    sys.exit(0)
