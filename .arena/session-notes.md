# Заметки между сессиями

## 2026-07-31 — вынос интерактива из Pyodide в статический JS + бандл модулей

Запрос пользователя: «весь проект был на Pyodide, из-за этого webapp
работал криво — довести до ума, использовать нужные языки, чтобы
сочетались и не ломали бота/админку». Сделано без смены общей архитектуры
(два стека, паритет обязателен) — точечно исправлены реальные причины
«кривой» работы браузерной панели:

- **Главный баг нашёлся, а не был на вид**: `webapp/pages/world_map.py`,
  `world_grid.py`, `dungeons.py` рисовали `<script>...</script>` ВНУТРИ
  HTML-строки, которую `webapp/dom.py:html()` вставляет через
  `node.innerHTML = markup`. Браузеры по спецификации НЕ выполняют
  `<script>`, попавший в DOM через `innerHTML` — то есть кисть по карте
  мира, drag-and-drop локаций на глобальной сетке и таймер порталов
  подземелий **не работали никогда**, хотя код выглядел рабочим и
  текстовые тесты (`test_pages.py`) его не ловили (они проверяют HTML-
  строку, а не выполнение в браузере).
- **Исправление**: весь этот интерактив перенесён в настоящий статический
  JS-файл `webapp/static/interactions.js`, подключённый обычным
  `<script src=... defer>` в `index.html` (не через Pyodide вообще).
  Слушатели навешаны делегированно на `document`, поэтому переживают
  любое число `app.render()`. Границу провели по типу задачи: Python
  считает правила и рисует HTML, JS отвечает только за события мыши/touch
  и зовёт `window.__app.*` (те же Python-методы `paint_cell`, `edit_cell`,
  `pick_brush`, `move_world_loc`, уже покрытые тестами).
- **Живые таймеры катаклизмов/часов** (`webapp/live_timer.py`) — оставлены
  на Python: это не разметка через innerHTML, а прямой вызов
  `js.setInterval` из Python (Pyodide), там inline-скрипт и не
  подразумевался. Таймер порталов подземелий переведён на чистую
  JS-арифметику дат (не нуждается в игровых данных вообще) —
  `interactions.js:tickDungeonTimers`.
- **Утечка pyodide-прокси**: `webapp/dom.py` раньше копил все
  `create_proxy(...)` в один список `_proxies` без освобождения — за
  долгую сессию с полусотней рендеров набирались сотни забытых
  обработчиков (жор памяти, тормоза на длинных сессиях). Теперь прокси
  разделены на `_scoped` (валидация форм/автосейв/превью/инлайн-
  редактирование — гасятся `.destroy()` в начале каждого `wire_forms()`,
  то есть перед каждым `render()`) и `_permanent` (один делегированный
  клик-слушатель + один таймер тоста — создаются один раз за сессию).
  Тост дополнительно избавлен от прокси на каждый вызов: один переиспользуемый
  `setTimeout`-хендлер + `clearTimeout` предыдущего.
- **Холодный старт ускорен**: раньше `index.html` делал fetch каждого из
  ~80 `.py`-файлов по отдельности (параллельно, но каждый — отдельный
  HTTP/TLS раунд-трип; на плохой мобильной сети это ощутимо дольше самого
  Pyodide). Добавлен `tools/build_bundle.py` — собирает всё содержимое
  `modules.json` в один `webapp/bundle.json` (~650 КБ, укладывается в
  лимит патчсета). `index.html` сначала пробует забрать бандл одним
  запросом; если бандла нет/битый/устарел — тихий откат на старый
  постфайловый fetch, так что бандл — ускорение, а не точка отказа.
  **Правило**: после правки любого модуля из `modules.json` нужно
  перезапустить `python3 tools/build_bundle.py` — `tests/test_wiring.py`
  сверяет sha256-digest бандла с содержимым файлов на диске и падает,
  если он отстал.
- **Тесты**: `tests/test_wiring.py` дополнен тремя блоками — актуальность
  и состав `webapp/bundle.json`; отсутствие `<script` в любом
  `webapp/pages/*.py` (значит, интерактив либо `data-act`, либо ушёл в
  `interactions.js`); синтаксическая валидность `interactions.js`
  (`node --check`, грейсфул-скип без node). `.arena/CONTEXT.md` обновлён
  новым разделом «где Python, а где JS» в стеке A.
- **Паритет и стек B не тронуты**: `admin/`, `bot/`, `core/` не менялись —
  там и так обычный веб-стек (FastAPI + Jinja2 + vanilla JS), никакого
  Pyodide не было. Все 25 наборов `tests/run_all.py` зелёные, включая
  ранее известные флейки (`test_dungeon.py` изредка падает на случайном
  сиде независимо от этой правки — воспроизведено и на `HEAD` до изменений).

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

## 2026-08-01 — Telegram-прокси для бота (Tor / SOCKS5): диагностика и понятные ошибки

Запрос пользователя: панель настроек показывала «Последняя ошибка бота: HTTP
Client says - ClientConnectorError: ... [Превышен таймаут семафора]» и сырое
«❌ In order to use aiohttp client for proxy requests, install aiohttp-socks»
(это RuntimeError aiogram, когда в окружении нет aiohttp-socks; в
requirements.txt пакет уже был, но устаревшее окружение его не имело).

- Новый модуль `bot/proxy.py` (только серверный стек, в modules.json не нужен):
  - `validate_proxy_url` — схема (socks4/5/5h/http/https), host:port, userinfo,
    IPv6; русские ошибки вместо английского исключения aiogram;
  - `error_tip` / `friendly_error` — сырую ошибку polling/старта превращает в
    подсказку («проверь, что Tor запущен и слушает 9150/9050», «установи
    pip install aiohttp-socks»), оригинал сохраняется внутри;
  - `check_proxy` — пошаговая диагностика для кнопки «🔌 Проверить»:
    адрес → наличие aiohttp-socks → TCP-проба порта → связь с
    api.telegram.org через прокси (стоп на первой неудаче, таймауты 4/10 с).
- `bot/runner.py` — пред-проверки в `start()` (битый адрес / нет пакета → сразу
  понятная ошибка), в `_poll()` и `except start()` ошибки через прокси
  заменяются на подсказку с оригиналом.
- Админка: `/api/proxy/check` (guard manage_settings), на /settings —
  предупреждение о не установленном aiohttp-socks, подсказка под «Последней
  ошибкой бота», кнопка «🔌 Проверить» рядом с полем прокси.
- Попутно: `launch.py:try_start_bot_from_db` (мёртвый код, но ловушка) теперь
  передаёт прокси; `TELEGRAM_PROXY_URL` задокументирован в `.env.example`.
- Тесты: `tests/test_proxy.py` (валидация, подсказки, check_proxy с моками,
  реальная TCP-проба на localhost), подключён в `tests/run_all.py`.

## 2026-08-01 — Кнопки на фото-экранах + конфликт двух экземпляров бота

Запрос пользователя: «не работает кнопка осмотреться» + логи с
`TelegramBadRequest: there is no text in the message to edit` (location.py
inspect_cell, battle.py rest) и бесконечным `TelegramConflictError: terminated
by other getUpdates request`.

- **Корень бага с кнопками**: экран локации и экран боя — это ФОТО с подписью
  (карта локации / портрет моба, `send_or_edit_photo`). Обработчики кнопок
  звали `callback.message.edit_text(...)`, а у фото-сообщения нет текста —
  Telegram отвечает «there is no text in the message to edit». Ломались не
  только «Осмотреться», а все кнопки на таких экранах (бой, отдых, сундук…).
- **Фикс**: новый `bot/utils/edit.py` — `safe_edit_text(event, text, ...)`:
  текстовое сообщение → edit_text; фото/видео → edit_caption (фото остаётся);
  нельзя отредактировать → шлёт новое сообщение; «message is not modified»
  проглатывается. Заменены ВСЕ 53 вызова `edit_text` в bot/handlers/*.py.
  В dungeon.py убран ставший лишним ручной обход для фото.
- **Конфликт getUpdates**: aiogram ретраит его бесконечно (в 3.30 нет события
  polling_error). Сделано: (1) `ConflictAwareSession(AiohttpSession)` ловит
  TelegramConflictError на уровне сессии; (2) `BotRunner._handle_conflict` —
  единичный конфликт переживаем, повторный (2+ за 2.5с) → `stop()` с
  понятным русским сообщением в панели; (3) `_start_lock` в start/stop —
  два параллельных start() (двойной клик «Запустить бота») больше не создают
  два polling-цикла; (4) `run.bat` больше НЕ запускает сервер дважды
  (убраны `start /B uvicorn` + `python launch.py` — было два процесса на
  одном порту, каждый мог поднять бота); (5) `launch.py` проверяет занятость
  порта и вежливо просит закрыть лишний экземпляр.
- **Тесты**: `tests/test_bot_edit.py` (safe_edit_text на фейковых сообщениях:
  текст/фото/ошибки), `tests/test_bot_runner.py` (двойной start → один polling,
  конфликт → остановка с объяснением, единичный конфликт → продолжение).
  В `test_bugfixes.py` обновлён страж `await callback.message.edit_text` →
  `await safe_edit_text` (тест резал исходник dungeon.py по этой строке).
