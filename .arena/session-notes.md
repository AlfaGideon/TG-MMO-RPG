# Заметки между сессиями

## 2026-07-31 — аудит багов поверх самописных тестов

Полный разбор: `AUDIT-BUGS.md`. Ключевое, что поменялось архитектурно:

- **Боевая очередь** (`p.combat["queue"]`) хранит dict `{"mob", "from"}`
  вместо int; `_entry_parts` в `engine/combat.py` читает и старый формат
  (старые сохранения не ломаются). `combat.start/join` принимают
  `origin` — ключ домашней клетки твари; `behavior.hunters_near` и
  `horde.prowl` возвращают `(mob_index, cell_key)`.
- **Аукцион (сервер)**: статусы лотов переключаются ТОЛЬКО через
  `_claim_lot` (атомарный условный UPDATE). Не возвращать прямое
  присваивание `lot.status = ...` в обход без разбора последствий.
- **Дата/время в `core/`**: паттерн «`datetime.now(timezone.utc)` +
  `_aware()` при чтении из БД». SQLite отдаёт naive, Postgres — aware.
  `datetime.utcnow()` в новом коде не использовать.
- **Имя персонажа** чистится `engine.rules.clean_name()` (server + admin).
  В браузерной панели имена НЕ чистим: рендер экранирует (test_pages).
- **Тесты**: серверные наборы молча скипаются без sqlalchemy/aiosqlite —
  `run_all.py` теперь предупреждает. Регрессии аудита:
  `tests/test_bugfixes.py`.
- **Незакрытый хвост** (см. AUDIT-BUGS.md A/B/C): идентичность вещи по
  индексу шаблона → семейство багов с дубликатами; `player.worn` никем
  не пишется (именные статы не применяются в бою браузерного стека);
  могилы без этажа в engine; дефолтный ADMIN_SECRET_KEY.

## 2026-07-31 — второй проход (бот-хендлеры, админка, гонки мира)

Полный разбор в `AUDIT-BUGS.md` («Второй проход», №10–19). Архитектурное:

- **Поюзерная сериализация апдейтов**: `bot/locks.py` +
  `bot/middlewares/serialize.py` — первым middleware для message и
  callback_query (порядок: Serialize → DB → Offline). Это корневой фикс
  всех гонок «двойной тап» (крафт, покупки, вскрытия).
- **«Отщёлкивание» общих ресурсов мира**: сундук (`location.open_chest`),
  могила (`core/death.claim` — атомарный DELETE до раздачи), захват моба
  (`battle.start_cell_battle`), HP/добивание босса (`worldevents.hit_boss`
  — HP через `UPDATE … SET hp = MAX(0, hp - n)`, награда за условным
  `is_active`). Везде инвариант «победитель ровно один» через rowcount.
- **`func.greatest` в SQLite нет** — использовать скалярный `func.max(0, …)`,
  работает в обеих БД.
- **Гонки репродуцировать только на файловой SQLite** (tempfile):
  `:memory:` StaticPool = одно соединение, гонку не увидеть.
- **Рестарт бота**: `BotRunner._cleanup_after_restart` снимает
  `engaged_by_id` со всех MobSpawn (иначе мобы-«заложники» без боя).
  Все fire-and-forget `create_task` держат ссылку в `_bg_tasks`.
- **Паритет смерти**: подземелье теперь зовёт `_lose_bag` (надгробие +
  пятина золота + рана), как поверхность и браузерный стек.
- **Админка**: `editor_cell_save` парсит числовые поля формы с сентинелом
  и отвечает 303 + баннер ошибки (`editor_cell.html`), а не 500 с
  откатом всей правки.
- **Зависимости для полного прогона**: `pip install --user
  "sqlalchemy[asyncio]" aiosqlite aiogram pillow fastapi jinja2
  python-multipart pydantic-settings` (в sandbox между сессиями
  ~/.local живёт). Без aiogram/fastapi соответствующие регрессии
  грейсфул-скипаются с ⚠.
- **Проверка «до»**: `git worktree add /tmp/orig HEAD` + прогон
  сценариев оттуда; не забыть `git worktree remove`.
