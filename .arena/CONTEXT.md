# Shadow Lands — контекст для AI-сессий

> Этот файл читается в начале каждой сессии вместо полного сканирования репозитория.
> Обновляй при появлении новых архитектурных решений, новых модулей и при смене приоритетов.

## Проект

**Shadow Lands** — Telegram MMORPG. Два независимых стека в одном репозитории.

| Стек | Технологии | Entry point | Где работает |
|---|---|---|---|
| A — GitHub Pages | Чистый Python + Pyodide в браузере | `index.html` → `webapp/boot.py` | `alfagideon.github.io` |
| B — Сервер | aiogram + FastAPI + SQLAlchemy | `launch.py` | Локально / Render / VPS |

Правило из `README.md`: новая игровая механика должна попасть в `engine/`, новый раздел панели — в `webapp/pages/` + `webapp/actions/`, и оба — в `modules.json`. `tests/test_wiring.py` проверяет это.

## Директории

```
admin/           серверная админ-панель (стек B): FastAPI + Jinja2 + vanilla CSS/JS
bot/             aiogram-бот (стек B)
core/            серверные модели, БД, игровая логика (стек B)
engine/          чистая игровая логика без зависимостей (общая для обоих стеков)
webapp/          клиентская админ-панель в браузере (стек A)
admin-login/     статическая прокладка входа для GitHub Pages
tests/           тесты
modules.json     манифест загрузки модулей в Pyodide
```

## Ключевые файлы

- `admin/main.py` — точка входа серверной админки. ~2900 строк, множество FastAPI-маршрутов.
- `admin/static/style.css` — единый CSS админки.
- `admin/templates/` — шаблоны Jinja2.
- `core/models.py` — SQLAlchemy-модели.
- `core/database.py` — инициализация БД и `async_session`.
- `engine/permissions.py` — ранги и точечные права админов.
- `bot/runner.py` — управление жизненным циклом бота.
- `launch.py` — запуск серверного стека.

## Текущий фокус

- Улучшение дизайна и UX серверной админ-панели (`admin/`).
- Поддержка курируемой документации для сокращения времени onboarding.

## Конвенции

- Роли админов: `viewer`, `moderator`, `admin` + точечные права `CAP_KEYS`.
- Проверка прав в админке: `guard(request, cap)` из `admin/main.py`.
- Все POST-редиректы используют `RedirectResponse(..., status_code=303)`.
- Шаблоны наследуют `base.html`.
- Статика раздаётся с `admin/static/` через `app.mount("/static", ...)`.

## Как работать с областями

| Задача | Смотреть сначала |
|---|---|
| Новый экран админки | `admin/ADMIN_README.md`, `admin/templates/base.html`, `admin/static/style.css` |
| Права доступа | `engine/permissions.py`, `admin/auth.py` |
| Игровая логика | `engine/` + `core/` |
| Бот | `bot/BOT_README.md` (если есть) или `bot/main.py`, `bot/runner.py` |
| База данных | `core/models.py`, `core/database.py` |

## Заметки между сессиями

См. `.arena/session-notes.md`.
