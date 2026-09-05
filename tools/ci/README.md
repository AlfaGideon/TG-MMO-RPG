# CI: готовый workflow для GitHub Actions

Файл `github-actions-ci.yml` — рабочая конфигурация непрерывной интеграции
для этого репозитория. Он лежит здесь, а не в `.github/workflows/`, по
технической причине: интеграция, которой сделан коммит (в том числе агент
2026-09-02 — push был отклонён с `refusing to allow a GitHub App to
create or update workflow ... without workflows permission`), не имеет
права `workflows`, и GitHub отклоняет push, создающий файлы в
`.github/workflows/`. Включить может только человек — способом ниже.

## Как включить (один раз, вручную)

```bash
mkdir -p .github/workflows
cp tools/ci/github-actions-ci.yml .github/workflows/ci.yml
git add .github/workflows/ci.yml
git commit -m "Включить CI"
git push
```

Либо через веб-интерфейс GitHub: **Actions → New workflow → set up a
workflow yourself**, вставить содержимое `github-actions-ci.yml`.

## Что проверяет workflow

1. `pip install -r requirements.txt` + `pytest`, `pytest-asyncio`
   (последние два не входят в `requirements.txt`: это зависимости тестов,
   а не приложения).
2. `python3 tests/run_all.py` — все наборы `tests/test_*.py`; скриптовые
   запускаются напрямую, pytest-наборы через `python3 -m pytest -q`.
3. `python3 tools/build_bundle.py` + `python3 tests/test_wiring.py` —
   манифест `modules.json`, `FALLBACK` в `index.html` и бандл согласованы.
4. Финальный шаг падает, если после сборки `webapp/bundle.json` или
   `index.html` отличаются от закоммиченных: это ровно тот случай, когда
   разработчик поправил `engine/` или `webapp/`, но забыл пересобрать
   бандл, и браузерная панель осталась бы на старом коде.

## Локальный эквивалент CI

Те же команды перед пушем:

```bash
python3 tests/run_all.py
python3 tools/build_bundle.py && python3 tests/test_wiring.py
python3 tests/test_bundle_integrity.py
git status --short webapp/bundle.json index.html   # должно быть пусто
```
