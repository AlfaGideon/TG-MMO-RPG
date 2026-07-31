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

## 2026-07-31 — дедуп Telegram-апдейтов (двойные /start и колбэки)

Симптом: один /start или help → две строки в логе и два ответа,
плюс `message is not modified` на повторном edit.

- **Браузерный стек** (`webapp/telegram.py`): `UpdateDeduper` (LRU update_id)
  + `_ingest` под asyncio.Lock; `start()` не плодит зомби-loop
  (`_halt_loop` await'ит cancel, `_loop_gen` гасит старый поллер).
- **Серверный стек** (`bot/middlewares/dedup.py`): `DedupUpdateMiddleware`
  первым на message/callback_query; `reset_deduper()` при каждом
  `BotRunner.start`.
- Регрессия: `tests/test_telegram_dedup.py` (в `run_all.py`).
- Если дубли останутся — проверь, что **не крутятся оба стека**
  (Pyodide-панель + launch.py) с одним токеном: дедуп внутри
  процесса, не между процессами.

## 2026-07-31 — AI-мастерская в админке (квесты/лор/диалоги)

- Блок: `/editor/ai` (меню «Контент мира → ✨ AI-мастерская»). Модули:
  `core/ai.py` (провайдеры, chat_complete через aiohttp, офлайн-режим),
  `core/lore.py` (досье мира + «библия лора» + промпты), модель
  `AIGeneration` (draft → bible → applied/discarded), шаблон
  `editor_ai.html`, роуты в `admin/main.py`.
- **Выбор провайдера** (по mnfst/awesome-free-llm-apis, июль 2026):
  основной — **Mistral** (256K контекст, ~1B токенов/мес free, FR — у
  владельца ЕС; free-tier Gemini из EU/UK недоступен, поэтому Gemini —
  опция, не дефолт). Альтернативы в UI: Groq, OpenRouter, GitHub Models,
  свой OpenAI-совместимый endpoint.
- **«Долгая память»** = досье мира в системном промпте (локации, NPC,
  квесты, мобы, боссы, фракции + записи со статусом bible), бюджеты в
  `core/lore.py` (60K/30K символов).
- **Без ключа работает офлайн-режим** (шаблоны из engine.data) — честно
  помечен в UI и в ответе API (`offline: true`).
- Ключ: AppSetting `ai_api_key`/провайдер/модель (приоритет над env
  AI_API_KEY и т.д.); в HTML только маска `xxx…yyyy`; сохранение маски
  ключ не затирает.
- Настоящие сетевые вызовы в тестах НЕ делаются: `chat_complete` гоняется
  против aiohttp-мок-сервера (200/429/401/мусор), эндпоинты — через
  FastAPI TestClient с тестовой SQLite (DATABASE_URL ставится ДО
  импорта admin.main; httpx нужен только тесту — гейтится).
- Попутно починен латентный баг: `base.html` + `request.state.get()` =
  500 на starlette 1.3 (AUDIT-BUGS.md №19.5).
