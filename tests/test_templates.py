"""Статическая проверка Jinja2-шаблонов админки.

Гоняет tools/check_templates.py: синтаксис всех шаблонов + отсутствие
вызовов встроенных функций Python (set(), len() и т.п.), которых нет
в окружении Jinja2, + ссылки на существующие extends/import.

Реальный кейс: {% set loc_dirs = connected_dirs.get(loc.id, set()) %}
в editor_world.html валил страницу редактора мира с
UndefinedError: 'set' is undefined — синтаксически шаблон был «правильный»,
поэтому без такой проверки баг доезжал до рантайма.

Запуск: python -m pytest tests/test_templates.py -v
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKER = os.path.join(ROOT, "tools", "check_templates.py")

pytest.importorskip("jinja2")

sys.path.insert(0, os.path.join(ROOT, "tools"))
import check_templates as ct  # noqa: E402


def test_all_templates_pass_static_checks():
    """Каждый шаблон в репо: валидный синтаксис, без builtin-вызовов."""
    proc = subprocess.run(
        [sys.executable, CHECKER],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"Проверка шаблонов провалилась (exit {proc.returncode}):\n"
        f"{proc.stdout}\n{proc.stderr}"
    )


def test_checker_detects_builtin_call(tmp_path, monkeypatch):
    """Вызов set() в шаблоне обязан быть пойман (тот самый баг)."""
    bad = tmp_path / "bad.html"
    bad.write_text(
        "{% set loc_dirs = connected_dirs.get(loc.id, set()) %}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ct, "TPL_DIR", str(tmp_path))
    problems = ct.check_template(str(bad))
    assert any("'set()'" in p for p in problems)


def test_checker_accepts_list_default(tmp_path, monkeypatch):
    """Правильная замена (список) проблем не даёт."""
    good = tmp_path / "good.html"
    good.write_text(
        "{% set loc_dirs = connected_dirs.get(loc.id, []) %}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ct, "TPL_DIR", str(tmp_path))
    assert ct.check_template(str(good)) == []


def test_checker_detects_missing_extends(tmp_path, monkeypatch):
    """Ссылка на несуществующий extends ловится."""
    bad = tmp_path / "orphan.html"
    bad.write_text("{% extends 'no_such_base.html' %}\n", encoding="utf-8")
    monkeypatch.setattr(ct, "TPL_DIR", str(tmp_path))
    problems = ct.check_template(str(bad))
    assert any("no_such_base.html" in p for p in problems)


def test_checker_detects_syntax_error(tmp_path, monkeypatch):
    """Сломанный синтаксис шаблона ловится."""
    bad = tmp_path / "broken.html"
    bad.write_text("{% if x %}\n", encoding="utf-8")
    monkeypatch.setattr(ct, "TPL_DIR", str(tmp_path))
    problems = ct.check_template(str(bad))
    assert problems
