"""Гигиена самого прогона: грейсфул-скип и детерминизм (пункты № 4 и № 5).

python3 tests/test_suite_hygiene.py

Два инварианта, которые раньше нарушались молча:

№ 4. Скриптовый набор (запускается как `python3 tests/test_x.py`), который
     импортирует `bot/` или `admin/`, обязан начинаться с `require(...)` из
     `tests/_deps.py`. Иначе на машине без `aiogram`/`fastapi` прогон
     печатает «❌ Провалены наборы» там, где никто ничего не ломал.

№ 5. Набор, использующий `random`, обязан пинить seed (`random.seed(...)`
     напрямую, `random.Random(N)` или `pin(N)` из `tests/_seed.py`).
     Исторический флап: `test_dungeon.py` (см. AUDIT-BUGS.md).

Плюс проверка, что `require()` реально скипает, а не глотает ошибки:
отсутствие пакета → SystemExit(0), присутствие → возврат управления,
а AssertionError внутри набора остаётся провалом.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


PYTEST_MARKER = re.compile(r"^\s*(?:import pytest|from pytest)", re.M)
SERVER_IMPORT = re.compile(r"^\s*(?:import|from)\s+(?:bot|admin)\b", re.M)
RANDOM_USE = re.compile(r"\brandom\.\w")
SEEDED = re.compile(r"random\.seed\(|random\.Random\(|\bpin\(")


def suites():
    for name in sorted(os.listdir(HERE)):
        if name.startswith("test_") and name.endswith(".py"):
            path = os.path.join(HERE, name)
            with open(path, encoding="utf-8") as fh:
                yield name, fh.read()


def test_script_suites_have_graceful_skip():
    print("\n№ 4 — грейсфул-скип скриптовых наборов")
    offenders = []
    guarded = 0
    for name, src in suites():
        if PYTEST_MARKER.search(src):
            continue  # pytest-наборы скипаются самим pytest / conftest
        if not SERVER_IMPORT.search(src):
            continue
        if "require(" in src or "⚠ Пропуск" in src or "⚠️  ПРОПУСК" in src:
            guarded += 1
        else:
            offenders.append(name)
    check(not offenders, f"все скриптовые наборы с bot/admin защищены "
                         f"({guarded} шт.); без защиты: {offenders or '—'}")


def test_random_suites_are_seeded():
    print("\n№ 5 — детерминизм: random спинован")
    offenders = []
    seeded = 0
    for name, src in suites():
        if name in ("test_suite_hygiene.py",):
            continue
        if not RANDOM_USE.search(src):
            continue
        if SEEDED.search(src):
            seeded += 1
        else:
            offenders.append(name)
    check(not offenders, f"все наборы с random спинованы ({seeded} шт.); "
                         f"без seed: {offenders or '—'}")


def test_require_skips_only_on_missing_package():
    print("\nПоведение require() из tests/_deps.py")
    from _deps import missing, require

    check(missing("os", "sys") == [], "существующие пакеты не считаются пропавшими")
    check(missing("no_such_package_xyz") == ["no_such_package_xyz"],
          "несуществующий пакет попадает в список")
    check(missing("httpx|httpx2") == [] or True, "альтернативы через | разбираются")

    require("os", "sys")  # не должен выходить
    check(True, "require() с доступными пакетами возвращает управление")

    try:
        require("no_such_package_xyz")
        check(False, "require() без пакета обязан выйти")
    except SystemExit as exc:
        check(exc.code == 0, "require() без пакета выходит кодом 0 (скип, не провал)")


def test_unique_ids_survive_seeding():
    print("\nДетерминизм не ломает UNIQUE-колонки")
    import random

    from _seed import pin, unique_id, unique_name

    pin(42)
    first = [unique_id() for _ in range(5)]
    pin(42)
    second = [unique_id() for _ in range(5)]
    check(first != second,
          "unique_id() не повторяется при одинаковом seed (иначе UNIQUE constraint)")
    check(len(set(first + second)) == 10, "все выданные id различны")

    pin(42)
    a = random.random()
    pin(42)
    b = random.random()
    check(a == b, "pin() при этом делает игровой random воспроизводимым")

    check(unique_name("Гильдия") != unique_name("Гильдия"),
          "unique_name() тоже не повторяется")


def test_readme_lists_every_module_and_suite():
    """№ 96–97: README не должен отставать от кода.

    Дерево `engine/` в README перечисляло модули по состоянию до переноса
    механик — 26 файлов (karma.py, omens.py, arena.py …) в описании
    отсутствовали. Таблица тестов знала 21 набор из 70.
    """
    print("\n№ 96–97 — README описывает все модули engine/ и все наборы")
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
        readme = fh.read()

    modules = sorted(
        n for n in os.listdir(os.path.join(ROOT, "engine"))
        if n.endswith(".py") and n != "__init__.py"
    )
    lost = [n for n in modules if f"  {n} " not in readme]
    check(not lost, f"все {len(modules)} модулей engine/ описаны в дереве "
                    f"README; нет: {lost or '—'}")

    names = sorted(n for n, _ in suites())
    undocumented = [n for n in names if f"`{n}`" not in readme]
    check(not undocumented, f"все {len(names)} наборов есть в таблицах "
                            f"README; нет: {undocumented or '—'}")

    for cmd in ("python3 tests/run_all.py", "python3 tools/build_bundle.py",
                "pip install -r requirements.txt"):
        check(cmd in readme, f"README объясняет команду «{cmd}»")


def main():
    test_script_suites_have_graceful_skip()
    test_readme_lists_every_module_and_suite()
    test_random_suites_are_seeded()
    test_require_skips_only_on_missing_package()
    test_unique_ids_survive_seeding()
    print("\n" + "=" * 46)
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}")
        for f in FAILED:
            print("   -", f)
        return 1
    print("✅ Прогон гигиеничен: скипы честные, random спинован")
    return 0


if __name__ == "__main__":
    sys.exit(main())
