# 🌑 Shadow Lands (TG-MMO-RPG) — 100 задач на доработку существующего проекта

> **Файл пересоздан:** 2026-08-14, на основе построчного аудита репозитория `TG-MMO-RPG`.
> **Предыдущая версия файла удалена полностью** — в ней были придуманные механики («мимики», «кредитные амнистии» и т. п.), которых в проекте нет. Это не аудит.
>
> **Правило этого документа:** здесь НЕТ ни одной новой игровой механики «с нуля». Каждая задача закрывает **конкретный пробел существующего кода**: система написана, но не подключена; подключена на сервере, но нет в `engine/`; есть в бою, но нет в админке; заявлена в тестах, но не запускается; обещана текстом статуса, но не реализована; есть в одном стеке и нет в другом.
>
> **Почему каждая задача — «точное ТЗ»:** каждый пункт содержит доказательство из репозитория (файл и строку), что уже есть, чего нет, точный список файлов и **измеримый критерий приёмки** (команда + ожидаемый вывод). Любая нейросеть или разработчик должны реализовать пункт одинаково или, если не могут, — объяснить, в чём расхождение с доказательством, а не «дописать по-своему».

## 📋 Легенда статусов

| Метка | Значение |
|---|---|
| ✅ сделано | Реализовано в сессии 2026-08-14, подтверждено тестом (тест указан в пункте) |
| ⬜ не сделано | Задача готова к реализации, ничего не начато |
| 🟡 частично | Часть закрыта, остаток описан в пункте |

---

## 🔎 Сводка аудита (факты, на которых построены все 100 пунктов)

Два независимых стека: **A — браузерный** (`engine/` + `webapp/`, Pyodide, манифест `modules.json`) и **B — серверный** (`core/` + `bot/` + `admin/`, SQLAlchemy + aiogram + FastAPI). Аудит 2026-08-14:

1. **21 подсистема в `core/` написана и протестирована, но не вызывается из продакшена** — импортируются только из `tests/` (AST-анализ всех импортов): `karma`, `omens`, `dialogue`, `archaeology`, `investments`, `pawnshop`, `blackmarket`, `lunar`, `salvage`, `guilds`, `mentorship`, `duels`, `prestige`, `bounty`, `illusions`, `bestiary`, `ambient`, `legends`, `runes`, `pets` (только админка), `auction_bid` (не импортируется **вообще нигде**, включая тесты).
2. **12 тестовых наборов существовали в `tests/`, но не запускались**: `tests/run_all.py` держал зашитый список из 41 набора, а `test_combat_synergies.py`, `test_craft_and_dungeon_hazards.py`, `test_deep_fixes.py`, `test_dungeon_and_arena.py`, `test_economy_and_lunar.py`, `test_faction_warfare.py`, `test_guilds_and_mentorship.py`, `test_lore_and_legends.py`, `test_miniapp_and_radar.py`, `test_omens_and_gathering.py`, `test_progression_and_karma.py`, `test_templates.py` в него не попали.
3. **`tests/run_all.py` предупреждал только об `sqlalchemy`/`aiosqlite`.** Без `aiogram`/`fastapi` 4 набора (`test_items_magic`, `test_progression`, `test_ui_images`, `test_start_flow`) падали с `ModuleNotFoundError` внутри прогона — это выглядело как честный провал, хотя причина в зависимостях.
4. **Паритет стеков стережёт `tests/test_parity.py`** — реестр механик. На 2026-08-14: **26 из 27 механик в обоих стеках**, один долг — «Трёхвалютная экономика» (причина зафиксирована в реестре). В `IDEAS-next.md` было устаревшее «20 из 20».
5. **`player.worn` в `engine/models.py:58` объявлен, читается в `engine/rules.py:24` (статы именных экземпляров), но его НЕ писал ни один файл** — в браузерном бою именные статы не работали, хотя серверный стек (`core/stats.sum_bonuses`) их применял. Это долг B из `AUDIT-BUGS.md`.
6. **`engine/death.bury()` не хранил этаж** — могила из подземелья светилась на поверхности. Зеркало уже исправленного серверного бага (п. 17 `AUDIT-BUGS.md`).
7. **`core/dialogue.py` дублировал пороги кармы ±150** отдельной копией, а сама система диалогов не вызывалась из бота (в `talk_npc` показывался только статичный `cell.npc_dialogue`).
8. **Админка (`admin/main.py`) не упоминает 13 подсистем вообще** (grep = 0 вхождений): investments, pawnshop, lunar, salvage, guilds, mentorship, duels, bounty, prestige, archaeology, omens, karma, blackmarket. Питомцы в админке есть (`editor_pets.html`).
9. **CI отсутствует**: в репозитории нет `.github/workflows/`.
10. **Карма обещала эффекты, которых не было**: текст статуса «+15% к лечению», «+20% к урону Тьмы», «защита от фатального удара» — реализованы не были (первые два — закрыты в этой сессии, третий остался).

---

## ✅ Что уже сделано в этой сессии (2026-08-14) — файлы и тесты

| Что | Файлы | Проверка |
|---|---|---|
| `run_all.py`: автодетект наборов + pytest-раннер + полная проверка зависимостей (12 забытых наборов включены) | `tests/run_all.py` | `python3 tests/run_all.py` — 54 набора |
| Карма: модуль движка + серверные пороги/поступки/эффекты | `engine/karma.py` (новый), `core/karma.py`, `engine/models.py` | `tests/test_karma_omens_engine.py`, `tests/test_parity.py` |
| Карма в бою, за могилы, за боссов, строка в профиле | `engine/combat.py`, `engine/worldboss.py`, `engine/death.py`, `engine/texts.py`; `bot/handlers/battle.py`, `bot/handlers/world_extra.py`, `bot/handlers/location.py`, `bot/utils/texts.py`, `core/worldevents.py` | `tests/test_karma_omens_engine.py` |
| Эффекты кармы: +15 % лечения, +20 % Тьмы | `engine/inventory.py`, `engine/combat.py`, `bot/handlers/inventory.py`, `bot/handlers/battle.py` | `tests/test_karma_omens_engine.py` |
| Знамения: единый каталог + кнопка в боте и в движке | `engine/omens.py` (новый), `core/omens.py`, `bot/handlers/world_extra.py`, `bot/keyboards/inline.py`, `engine/game.py` | `tests/test_karma_omens_engine.py`, `tests/test_omens_and_gathering.py` |
| Реактивные диалоги NPC подключены к боту | `bot/handlers/location.py` (`talk_npc`), `core/dialogue.py` | прогон `run_all.py` |
| `player.worn` пишется при надевании и читается в бою (именные статы работают) | `engine/inventory.py`, `engine/items.py` (`resolve_owned`), `engine/rules.py`, `engine/combat.py`, `engine/game.py`, `engine/worldboss.py` | `tests/test_karma_omens_engine.py` |
| Могила хранит этаж гибели (паритет с серверным фиксом) | `engine/death.py` | `tests/test_karma_omens_engine.py` |
| Поля `bronze`/`silver`/`karma_score` у `Player` + кошелёк в профиле | `engine/models.py`, `engine/texts.py` | `tests/test_karma_omens_engine.py` |
| Реестр паритета: +«Карма», +«Знамения», проверка чисел кармы и каталога знамений | `tests/test_parity.py` | `python3 tests/test_parity.py` |
| Манифест и бандл пересобраны | `modules.json`, `index.html` (FALLBACK), `webapp/bundle.json` | `python3 tests/test_wiring.py` |
| Устаревшее «20 из 20» → «26 из 27» | `IDEAS-next.md` | — |
| **Партия 2 (та же дата):** разбор вещей и ломбард — кнопки в карточке вещи + экран займов | `bot/handlers/inventory.py`, `bot/keyboards/inline.py` | `tests/test_bot_entrypoints.py` |
| Археология: «Копать» и «Выкопать клад по карте» на клетке | `bot/handlers/location.py`, `bot/keyboards/inline.py` | `tests/test_bot_entrypoints.py` |
| Инвестиции: экран вклада + фоновая выплата дивидендов раз в сутки | `bot/handlers/location.py`, `core/investments.py` (`pay_dividends`), `bot/runner.py` (`_dividend_loop`) | `tests/test_bot_entrypoints.py` |
| Чёрный рынок: витрина и покупка | `bot/handlers/location.py`, `bot/keyboards/inline.py` | `tests/test_bot_entrypoints.py` |
| Фаза луны в осмотре клетки | `bot/handlers/location.py` | `tests/test_bot_entrypoints.py` |
| Благословение света: защита от фатального удара (все точки смерти) | `bot/handlers/battle.py`, `engine/combat.py` | `tests/test_karma_omens_engine.py`, `tests/test_bot_entrypoints.py` |
| CI: прогон 56 наборов + контроль забытой пересборки бандла | `tools/ci/github-actions-ci.yml` + `tools/ci/README.md` (новые) | GitHub Actions после ручной активации |
| Целостность бандла: sha256-сверка всех 85 модулей с диском | `tests/test_bundle_integrity.py` (новый) | `python3 tests/test_bundle_integrity.py` |
| Миграция старых сейвов движка под новые поля | `tests/test_karma_omens_engine.py` | тот же набор |

---

## Раздел 1. Тестовая инфраструктура и CI (№ 1–10)

### № 1. `run_all.py` запускает ВСЕ наборы `tests/` автоматически
**Статус:** ✅ сделано. **Тип пробела:** забытые тесты.
**Доказательство:** `tests/run_all.py` держал зашитый `SUITES = [...]` из 41 набора; в каталоге лежало 52 `test_*.py` — 12 pytest-наборов не запускались (`test_progression_and_karma.py`, `test_omens_and_gathering.py`, `test_templates.py`, `test_economy_and_lunar.py` и др.).
**Сделано:** `run_all.py` сам находит `tests/test_*.py` (сортировка по имени — детерминизм), файлы с `import pytest` запускает через `python3 -m pytest -q`, остальные — как скрипты.
**Критерий приёмки:** `python3 tests/run_all.py` → в логе видны все 54 набора, включая `test_progression_and_karma.py`; итог «✅ Все наборы пройдены (54)».

### № 2. `run_all.py` проверяет ВЕСЬ список зависимостей, а не только БД
**Статус:** ✅ сделано. **Тип пробела:** ложные провалы.
**Доказательство:** старый код проверял только `sqlalchemy`/`aiosqlite`; без `aiogram`/`fastapi` наборы `test_items_magic.py`, `test_progression.py`, `test_ui_images.py`, `test_start_flow.py` падали с `ModuleNotFoundError` (репродуцировано 2026-08-14).
**Сделано:** `DEPS` = `sqlalchemy`, `aiosqlite`, `aiogram`, `fastapi`, `Pillow`, `jinja2`, `httpx2`, `aiohttp`, `pytest`; при отсутствии печатается список и причина, прогон в конце повторяет предупреждение.
**Критерий приёмки:** при удалённом `aiogram` прогон начинается с «⚠️ ВНИМАНИЕ: не установлены зависимости: aiogram (сценарии бота)…».

### № 3. GitHub Actions CI: прогон тестов и сборка бандла на каждый push
**Статус:** ✅ сделано. **Тип пробела:** нет CI.
**Доказательство:** `.github/workflows/` в репозитории отсутствовал.
**Сделано:** готовый workflow `tools/ci/github-actions-ci.yml` + инструкция `tools/ci/README.md` — `ubuntu-latest`, Python 3.11, кеш pip; шаги: установка `requirements.txt` + `pytest`/`pytest-asyncio`; `python3 tests/run_all.py`; пересборка бандла и `python3 tests/test_wiring.py`; финальный шаг падает, если `webapp/bundle.json`/`index.html` не закоммичены после сборки.
**Почему не в `.github/workflows/`:** GitHub отклоняет push такого файла от интеграции без права `workflows` (`refusing to allow a GitHub App to create or update workflow`). Активация — одна ручная команда из `tools/ci/README.md`.
**Критерий приёмки:** после копирования файла в `.github/workflows/ci.yml` push запускает workflow; забытая пересборка бандла красит CI в красный с подсказкой команды.

### № 4. Скриптовые наборы мягко пропускаются без необязательных зависимостей
**Статус:** ⬜ не сделано. **Тип пробела:** нестабильный прогон на «голой» машине.
**Доказательство:** до установки зависимостей 4 набора падали `ModuleNotFoundError: No module named 'aiogram'` на `bot/handlers/__init__.py` — серверные наборы при этом умеют грейсфул-скип (паттерн `except ImportError: check(True, "пропуск")` в `tests/test_parity.py:test_shared_numbers_match`).
**ТЗ:** в каждом скриптовом наборе, импортирующем `bot/` или `admin/`, обернуть импорт в `try/except ImportError` с печатью «⚠ Пропуск: нет aiogram/fastapi» и выходом 0 — ровно как это сделано в серверных наборах. Перечислить такие наборы заранее: `test_items_magic.py`, `test_progression.py`, `test_ui_images.py`, `test_start_flow.py`, `test_bot_ui.py`, `test_bot_photos.py`, `test_admin_layout.py`, `test_admin_realtime.py`, `test_admin_logs.py`, `test_bot_runner.py`, `test_pets_admin.py`.
**Критерий приёмки:** на машине без `aiogram` прогон заканчивается «⚠️ … пропущена из-за отсутствующих зависимостей», а не «❌ Провалены наборы».
**Что НЕ делать:** не прятать реальные падения — скип разрешён только при `ImportError`, не при `AssertionError`.

### № 5. Пинить `random.seed` в каждом недетерминированном наборе
**Статус:** ⬜ не сделано. **Тип пробела:** флаки.
**Доказательство:** `AUDIT-BUGS.md`, раздел «Прочее на заметку»: «Первый прогон run_all.py однажды поймал флап в test_dungeon.py… вероятно, недетерминированность рандома; рекомендовано пиновать random.seed во всех наборах».
**ТЗ:** в каждом наборе, который использует `random` (проверить grep-ом `random.`), в начале `main()`/модуля добавить `random.seed(N)` с уникальной константой N для набора; добавить комментарий `# детерминизм: ...`.
**Файлы:** все `tests/test_*.py` с использованием `random`.
**Критерий приёмки:** три прогона подряд `python3 tests/run_all.py` дают одинаковый результат (0 флапов); проверка `grep -L "random.seed" $(grep -l "random\." tests/test_*.py)` пуста.

### № 6. Реестр паритета — обязательный шаг при каждом переносе механики
**Статус:** ✅ сделано (для кармы и знамений), остальное — правило на будущее. **Тип пробела:** паритет без стража.
**Доказательство:** `tests/test_parity.py` — `REGISTRY` (25 → 27 записей в этой сессии), `test_new_engine_modules_registered` падает, если новый игровой модуль `engine/` не зарегистрирован; `test_shared_numbers_match` сверяет общие константы.
**ТЗ (правило):** каждый пункт Раздела 2 этого файла при реализации ОБЯЗАН: (1) добавить `Feature(...)` в `REGISTRY`; (2) если в механике есть числа — добавить сравнение в `test_shared_numbers_match`; (3) запустить `python3 tests/test_parity.py` до и после.
**Критерий приёмки:** `test_parity.py` падает на «забытый» модуль до добавления строки и зелёный после.

### № 7. Тест целостности бандла: `bundle.json` содержит все модули `modules.json`
**Статус:** ✅ сделано (вместе с № 9 — одним набором). **Доказательство:** `tests/test_wiring.py` сверял манифест с `FALLBACK`, но не заглядывал внутрь `webapp/bundle.json`.
**Сделано:** `tests/test_bundle_integrity.py` — состав и порядок модулей бандла совпадают с `modules.json`, нет пропущенных и нет модулей-призраков.
**Критерий приёмки:** проверено вручную — подмена содержимого `engine/karma.py` в бандле роняет тест с именем модуля и подсказкой «запусти python3 tools/build_bundle.py».

### № 8. Сквозной pytest-сценарий: новые точки входа бота
**Статус:** ✅ сделано (шире, чем планировалось). **Сделано:** `tests/test_bot_entrypoints.py` (10 тестов): наличие кнопок (`inspect_keyboard`, `item_book_keyboard`, `main_menu_keyboard`), регистрация хендлеров в роутерах через реальное сопоставление magic-фильтров + негативная проверка, и доменные сценарии — археология (5 фрагментов → карта → клад, промах по координатам), дивиденды инвестиций, залог/выкуп в ломбарде, покупка на чёрном рынке без денег и с деньгами, карма и благословение, детерминизм фаз луны.
**Было (для истории):** нет интеграционного покрытия новых точек входа.
**Доказательство:** в этой сессии карма вшита в `bot/handlers/battle.py:_finish_victory`, `bot/handlers/world_extra.py:claim_grave`, `bot/handlers/location.py:harvest_ash`, знамения — в `world_extra.omens_menu`; unit-проверки есть (`tests/test_karma_omens_engine.py`), а сценария «победил зомби → в профиле карма +2 → открыл меню → увидел знамение» — нет.
**ТЗ:** pytest-набор `tests/test_karma_bot_flow.py` по образцу `tests/test_omens_and_gathering.py` (in-memory SQLite через `async_session`): (1) создать персонажа; (2) вызвать `bot.handlers.battle._finish_victory` с зомби → `character.karma_score == KILL_UNDEAD`; (3) вызвать `claim_grave` на чужой могиле → карма уменьшилась на `GRAVE_LOOT`; (4) `core.omens.omen_banner()` содержит «Знамение».
**Критерий приёмки:** набор входит в автодетект `run_all.py` и зелёный.

### № 9. Смоук-тест бандла: JSON валиден и содержимое актуально
**Статус:** ✅ сделано. **Доказательство:** при ошибке склейки или забытой пересборке панель на холодном старте берёт старый код, а тесты остаются зелёными (они импортируют файлы напрямую).
**Сделано:** `tests/test_bundle_integrity.py` — валидность JSON, наличие ключей `packages/modules/files/digest`, и сверка содержимого всех 85 модулей с диском по `sha256`.
**Критерий приёмки:** правка `engine/*.py` без пересборки → тест падает с именем модуля; после `python3 tools/build_bundle.py` — зелёный (проверено).

### № 10. Регрессии этой сессии: карма, знамения, worn, этажи могил
**Статус:** ✅ сделано. **Тип пробела:** нет регрессий на новые фиксы.
**Доказательство:** новый набор `tests/test_karma_omens_engine.py` — 31 проверка: кламп/пороги/поступки кармы, карма в бою (зомби +2, ворг 0), единый каталог знамений, `player.worn` (uid пишется, статы экземпляра 37 = 37 в бою, снятие чистит), могила с этажом (нет на поверхности, есть на этаже, ключ карты `3:1:3:3`), мародёрство −3, кнопка «Знамения» в меню, строка кармы в профиле, три валюты у `Player`.
**Критерий приёмки:** `python3 tests/test_karma_omens_engine.py` → «✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ».

## Раздел 2. Паритет: перенос серверных подсистем `core/` в браузерный стек `engine/` (№ 11–35)

> **Общее доказательство для раздела.** AST-анализ импортов 2026-08-14: перечисленные ниже модули `core/` импортируются только из `tests/` (или админкой) — в `engine/` их близнецов нет. Правило проекта (`README.md`, «Паритет стеков обязателен») требует каждую механику в обоих стеках; страхом служит `tests/test_parity.py` (см. № 6).
> **Общий шаблон ТЗ для № 11–35:** (1) создать `engine/<name>.py` с теми же константами и функциями, что в `core/<name>.py` (числа — идентично, единый каталог контента класть в `engine/`, а `core/` переключить на реэкспорт — паттерн `core/omens.py` и `core/worldevents.py`); (2) добавить точки входа в движке (боевые/мирные экраны, см. «Файлы» пункта); (3) зарегистрировать `Feature` в `tests/test_parity.py` и добавить сверку чисел; (4) добавить модуль в `modules.json` + `FALLBACK` в `index.html`; (5) `python3 tools/build_bundle.py`; (6) pytest-проверки. **Приёмка у всех одинаковая:** `python3 tests/test_parity.py` зелёный, `python3 tests/test_wiring.py` зелёный, новый pytest-набор зелёный, пункт № 6 выполнен.

### № 11. `engine/archaeology.py` — фрагменты скрижалей и карта сокровищ
**Статус:** ⬜ не сделано. **Доказательство:** `core/archaeology.py:find_relic_fragment` — 5 фрагментов → `treasure_map_coord = "loc:{id}:x:{x}:y:{y}"`; колонки `core/models.py:315-316` (`relic_fragments`, `treasure_map_coord`); в `engine/` модуля нет.
**ТЗ:** перенести `find_relic_fragment` и формат координат в `engine/archaeology.py` (Player-поля `relic_fragments`, `treasure_map_coord` добавить в `engine/models.py`); точка входа — действие «⛏ Копать» на клетке (роутер `engine/game.py` + кнопка в `engine/explore.py`), сбор 5-го фрагмента сообщает координаты тайника.
**Файлы:** `engine/archaeology.py` (новый), `engine/models.py`, `engine/game.py`, `engine/explore.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 12. `engine/spectral.py` — призрачный торговец и прах предков
**Статус:** ⬜ не сделано. **Доказательство:** `core/spectral.py` — `SPECTRAL_WARES` (`spec_wound_heal` 30, `spec_ethereal_blade` 75, `spec_ancestor_tear` 50 праха), `harvest_soul_ash`, `buy_spectral_item`; колонка `core/models.py:296` (`soul_ash`); в боте вход есть (`bot/handlers/location.py:spectral_nomad_menu`, `harvest_ash`), в `engine/` — нет.
**ТЗ:** `engine/spectral.py` с тем же каталогом (каталог — в `engine/`, `core/spectral.py` реэкспортирует); в движке: сбор праха с могилы (там же, где `engine/death.claim`) и меню призрака на могильных клетках.
**Файлы:** `engine/spectral.py` (новый), `engine/death.py`, `engine/game.py`, `core/spectral.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 13. `engine/investments.py` — вклады в лавки и дивиденды
**Статус:** ⬜ не сделано. **Доказательство:** `core/investments.py:invest_in_town` (списание через `engine.currency.total_in_bronze/deduct_currency`, ошибки «Сумма должна быть больше нуля.», «Не хватает …🟤.»), модель `TownInvestment` (`core/models.py:1313` `invested_bronze`); в `engine/` нет.
**ТЗ:** перенести вклад/дивиденды в `engine/investments.py`; в движке — пункт «🏦 Вклад в лавку» в меню безопасной локации (`engine/game.py`, экран `engine/explore.py`), выплата дивидендов по таймеру (`engine/respawn.py`-стиль, общий тик мира).
**Файлы:** `engine/investments.py` (новый), `engine/models.py`, `engine/game.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 14. `engine/pawnshop.py` — ломбард
**Статус:** ⬜ не сделано. **Доказательство:** `core/pawnshop.py` (модель `PawnLoan`, `core/models.py:1329` `loan_bronze`), импортируется только из `tests/test_economy_and_lunar.py`.
**ТЗ:** перенести залог/выкуп/просрочку в `engine/pawnshop.py`; в движке — NPC-ростовщик в Погосте (кнопка в `engine/explore.py`, роутер в `engine/game.py`).
**Файлы:** `engine/pawnshop.py` (новый), `engine/game.py`, `engine/explore.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 15. `engine/blackmarket.py` — чёрный рынок
**Статус:** ⬜ не сделано. **Доказательство:** `core/blackmarket.py` — витрина, импорт только из `tests/test_economy_and_lunar.py`; просроченные залоги по плану перетекают из ломбарда (см. № 14 и № 47).
**ТЗ:** `engine/blackmarket.py` (те же товары/цены); вход в движке — отдельная кнопка у теневого NPC (не смешивать с обычной лавкой).
**Файлы:** `engine/blackmarket.py` (новый), `engine/game.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 16. `engine/lunar.py` — фазы луны
**Статус:** ⬜ не сделано. **Доказательство:** `core/lunar.py` — фазы и эффекты, импорт только из `tests/test_economy_and_lunar.py`.
**ТЗ:** перенести расчёт фазы по дате в `engine/lunar.py` (без БД — чистая функция от `time.time()`); показывать фазу в `engine/texts.cell_view` и в бою применять её модификаторы там, где это делает сервер (`core/lunar.py` читать как эталон).
**Файлы:** `engine/lunar.py` (новый), `engine/texts.py`, `engine/combat.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 17. `engine/salvage.py` — разбор вещей на материалы
**Статус:** ⬜ не сделано. **Доказательство:** `core/salvage.py`, импорт только из `tests/test_economy_and_lunar.py`; крафт в движке есть (`engine/craft.py`), материалов из разбора нет.
**ТЗ:** `engine/salvage.py` с теми же таблицами выхода материалов; кнопка «🔧 Разобрать» в карточке предмета (`engine/inventory.card`) с выдачей в материалы крафта (`engine/craft.py`).
**Файлы:** `engine/salvage.py` (новый), `engine/inventory.py`, `engine/itemui.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 18. `engine/gathering.py` — травничество и сбор праха
**Статус:** ⬜ не сделано. **Доказательство:** `core/gathering.py:gather_herbs` — в боте вход есть (`bot/handlers/location.py:gather_herbs`), в `engine/` нет.
**ТЗ:** `engine/gathering.py` (травы на клетках с травой/лесом — тайлы уже размечены в `engine/world.py`); действие «🌿 Собрать травы» в `engine/explore.py`.
**Файлы:** `engine/gathering.py` (новый), `engine/explore.py`, `engine/game.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 19. `engine/familiars.py` — фамильяры
**Статус:** ⬜ не сделано. **Доказательство:** `core/familiars.py` (`FAMILIARS`, `familiar_card_text`, `set_familiar`), колонка `core/models.py:291` (`familiar_type`); в боте вход есть (`bot/handlers/character.py:familiar_menu`), в `engine/` нет.
**ТЗ:** `engine/familiars.py`; экран фамильяра в профиле движка (`engine/texts.profile` + кнопка в `engine/game.menu`); покупка за валюту через `engine/currency.deduct_currency`.
**Файлы:** `engine/familiars.py` (новый), `engine/models.py`, `engine/texts.py`, `engine/game.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 20. `engine/pets.py` — питомцы (сейчас только админ-редактор)
**Статус:** ⬜ не сделано. **Доказательство:** `core/pets.py` импортируется только из `admin/main.py` и `tests/test_pets_admin.py`; шаблон `PetTemplate` в `core/models.py`; в `engine/` питомцев нет вообще.
**ТЗ:** `engine/pets.py` (выбор питомца из `PetTemplate`, эффекты); в движке — вкладка питомца в профиле; в админке Pyodide (`webapp/pages/content.py`) — редактор шаблонов питомцев (паритет с `admin/main.py` + `editor_pets.html`).
**Файлы:** `engine/pets.py` (новый), `engine/models.py`, `engine/texts.py`, `webapp/pages/content.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 21. `engine/prestige.py` — престиж после капа
**Статус:** ⬜ не сделано. **Доказательство:** `core/prestige.py`, импорт только из `tests/test_progression_and_karma.py`; пункт 5 «Прогресс после капа» из `IDEAS-next.md` не закрыт.
**ТЗ:** `engine/prestige.py` (сброс уровня за постоянный бонус, те же числа); в движке — действие «♻ Престиж» в профиле при достижении капа уровня.
**Файлы:** `engine/prestige.py` (новый), `engine/texts.py`, `engine/game.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 22. `engine/subclasses.py` — подклассы
**Статус:** ⬜ не сделано. **Доказательство:** `core/subclasses.py` подключён в `core/stats.py` (влияет на статы) и тестируется в `tests/test_progression_and_karma.py`; в `engine/` нет.
**ТЗ:** `engine/subclasses.py` с теми же таблицами подклассов; применение в `engine/rules.stats`; выбор подкласса — экран в профиле (`engine/game.py`).
**Файлы:** `engine/subclasses.py` (новый), `engine/rules.py`, `engine/texts.py`, `engine/game.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 23. `engine/talents.py` — таланты
**Статус:** ⬜ не сделано. **Доказательство:** `core/talents.py` подключён в `core/stats.py` и тестируется в `tests/test_progression_and_karma.py`; в `engine/` нет.
**ТЗ:** `engine/talents.py` (дерево, стоимость очков — числа из `core/talents.py`); очки талантов за уровни (рядом с `engine/rules.add_exp`); экран распределения в профиле.
**Файлы:** `engine/talents.py` (новый), `engine/rules.py`, `engine/game.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 24. `engine/titles.py` — титулы
**Статус:** ⬜ не сделано. **Доказательство:** `core/titles.py` подключён в `core/stats.py` и тестируется в `tests/test_progression_and_karma.py`; в `engine/` нет.
**ТЗ:** `engine/titles.py` (условия получения — числа из `core/titles.py`); проверка условий там же, где растут `p.kills`/репутация (`engine/rules.py`, `engine/factions.py`); титул в `engine/texts.profile` рядом со строкой кармы.
**Файлы:** `engine/titles.py` (новый), `engine/rules.py`, `engine/factions.py`, `engine/texts.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 25. `engine/runes.py` — руны
**Статус:** ⬜ не сделано. **Доказательство:** `core/runes.py`, импорт только из `tests/test_craft_and_dungeon_hazards.py`; крафт/заточка в движке есть (`engine/craft.py`).
**ТЗ:** `engine/runes.py`; применение рун к именным экземплярам через реестр `engine/items.py`; экран в мастерской (`engine/trade.py`).
**Файлы:** `engine/runes.py` (новый), `engine/items.py`, `engine/trade.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 26. `engine/guilds.py` — гильдии
**Статус:** ⬜ не сделано. **Доказательство:** `core/guilds.py`, импорт только из `tests/test_guilds_and_mentorship.py`.
**ТЗ:** `engine/guilds.py` (создание/вступление/роли — по API `core/guilds.py`); хранение в `engine/storage.py` (настройки Store); экран гильдии в `engine/party.py` (социальный блок).
**Файлы:** `engine/guilds.py` (новый), `engine/storage.py`, `engine/party.py`, `engine/game.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 27. `engine/mentorship.py` — наставничество
**Статус:** ⬜ не сделано. **Доказательство:** `core/mentorship.py`, импорт только из `tests/test_guilds_and_mentorship.py`.
**ТЗ:** `engine/mentorship.py` (связка наставник–ученик, бонус опыта — числа из `core/mentorship.py`); кнопки в `engine/party.py` и `engine/social.py`.
**Файлы:** `engine/mentorship.py` (новый), `engine/party.py`, `engine/social.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 28. `engine/duels.py` — дуэли
**Статус:** ⬜ не сделано. **Доказательство:** `core/duels.py`, импорт только из `tests/test_guilds_and_mentorship.py`; в боте входа нет (пункт 3 `IDEAS-next.md` не закрыт).
**ТЗ:** `engine/duels.py` (вызов на одной клетке, пошагово через `engine/combat.py` между двумя `Player`); кнопка «⚔ Дуэль» у другого героя на клетке (`engine/mapview.py` → `engine/social.py`).
**Файлы:** `engine/duels.py` (новый), `engine/social.py`, `engine/game.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 29. `engine/arena.py` — арена теневых клонов
**Статус:** ⬜ не сделано. **Доказательство:** `core/arena.py` подключён в боте (`bot/handlers/world_extra.py:arena_menu_handler`, модель `CharacterShadow`); в `engine/` арены нет.
**ТЗ:** `engine/arena.py` (бой с тенью — копия героя с множителями из `core/arena.py`); вход — арена в Погосте (`engine/game.py` + `engine/social.py`).
**Файлы:** `engine/arena.py` (новый), `engine/social.py`, `engine/game.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 30. `engine/bounty.py` — награды за головы
**Статус:** ⬜ не сделано. **Доказательство:** `core/bounty.py`, импорт только из `tests/test_omens_and_gathering.py`.
**ТЗ:** `engine/bounty.py` (заказы на тварей — таблицы из `core/bounty.py`); доска наград в Погосте (`engine/quests.py`-стиль: экран + `on_kill`).
**Файлы:** `engine/bounty.py` (новый), `engine/quests.py`, `engine/game.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 31. `engine/illusions.py` — иллюзии
**Статус:** ⬜ не сделано. **Доказательство:** `core/illusions.py`, импорт только из `tests/test_lore_and_legends.py`.
**ТЗ:** `engine/illusions.py`; применение иллюзии к клетке/герою; экран в `engine/social.py` или `engine/explore.py` (где именно — по месту вызова серверного аналога в будущем боте, см. № 56).
**Файлы:** `engine/illusions.py` (новый), `engine/social.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 32. `engine/bestiary.py` — бестиарий
**Статус:** ⬜ не сделано. **Доказательство:** `core/bestiary.py`, импорт только из `tests/test_lore_and_legends.py`; `Player.kills` в движке уже считается (`engine/rules.py:_reward`).
**ТЗ:** `engine/bestiary.py` (записи по убитым тварям — данные уже есть в `engine/content.py:MOBS`); экран в меню (`engine/game.menu`), счётчик по видам из `p.kills` + новой структуры учёта по индексам мобов.
**Файлы:** `engine/bestiary.py` (новый), `engine/game.py`, `engine/models.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 33. `engine/ambient.py` — фоновые события мира
**Статус:** ⬜ не сделано. **Доказательство:** `core/ambient.py`, импорт только из `tests/test_miniapp_and_radar.py`; фоновые циклы в боте есть (`bot/runner.py:_portal_sweep_loop`, `_spawn_tick_loop`), в движке фонового тика нет.
**ТЗ:** `engine/ambient.py` (случайные фоновые строки/события по таймеру); вызов из тика мира в `engine/game.do_world` или `engine/respawn.py`.
**Файлы:** `engine/ambient.py` (новый), `engine/game.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 34. `engine/legends.py` — летопись рекордов
**Статус:** ⬜ не сделано. **Доказательство:** модель `ServerRecord` (`core/models.py`) используется только в `core/legends.py`; игрокам летопись не показывается ни в одном стеке.
**ТЗ:** `engine/legends.py` (записи «первый босс», «крупнейший катаклизм» — там же, где они уже пишутся: `engine/worldboss.py:_finish`, `engine/cataclysm.py`); экран «📖 Летопись» в меню; сервер: показ летописи в боте (см. № 60).
**Файлы:** `engine/legends.py` (новый), `engine/worldboss.py`, `engine/cataclysm.py`, `engine/game.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 35. `engine/dialogue.py` — реактивные реплики NPC
**Статус:** 🟡 частично (сервер подключён, движок — нет). **Доказательство:** `core/dialogue.py:generate_reactive_dialogue` подключён к боту в этой сессии (`bot/handlers/location.py:talk_npc`); в `engine/` аналога нет — NPC движка всегда говорят статичный текст.
**ТЗ:** `engine/dialogue.py` (та же логика ветвления: осада → катаклизм → караван → карма; пороги из `engine/karma.py`); использовать в `engine/explore.py` при осмотре NPC, контекст брать из `engine/cataclysm.py` (активное бедствие) и `engine/merchant.py` (караван).
**Файлы:** `engine/dialogue.py` (новый), `engine/explore.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

---

## Раздел 3. Подсистемы `core/` написаны и протестированы — но у игрока нет входа в боте (№ 36–60)

> **Общее доказательство для раздела.** AST-анализ 2026-08-14: модули ниже импортируются только из `tests/`; ни один роутер `bot/handlers/` их не вызывает. Игрок физически не может добраться до этих механик.
> **Общий шаблон ТЗ:** (1) точка входа = новый callback в существующем обработчике (кнопка + хендлер); (2) вся логика остаётся в `core/` (уже протестирована); (3) тексты ответов — в стиле существующих экранов; (4) событие в `core/realtime.py` (`publish`) для живой ленты админки; (5) pytest-сценарий входа. **Приёмка:** сценарий «нажал кнопку → увидел экран → действие изменило БД» в pytest-наборе.

### № 36. Карма в бою — упокоение нежити
**Статус:** ✅ сделано. **Доказательство:** было — `core/karma.py` импортировался только тестами; стало — `bot/handlers/battle.py:_finish_victory` вызывает `core_karma.on_kill(character, mob)` и дописывает строку «✨ Карма: +2…» в экран победы; нежить определяется по `UNDEAD` из `core/karma.py`.
**Проверка:** `tests/test_karma_omens_engine.py` + прогон `run_all.py`.

### № 37. Карма за разграбление чужих могил
**Статус:** ✅ сделано. **Доказательство:** `bot/handlers/world_extra.py:claim_grave` (чужая могила → `on_grave_loot`) и `bot/handlers/location.py:harvest_ash` (прах с могилы → тот же штраф −3), строка «💀 Карма: −3…» в ответах.
**Проверка:** `tests/test_karma_omens_engine.py` (движок) + `run_all.py` (бот).

### № 38. Карма за победу над мировым боссом
**Статус:** ✅ сделано. **Доказательство:** `core/worldevents.py:_reward_boss` — каждому участнику с долей ≥ MIN_SHARE `core_karma.change_karma(ch, KILL_BOSS)`; в движке — `engine/worldboss.py:_reward_all`.
**Проверка:** `tests/test_karma_omens_engine.py`, `tests/test_faction_warfare.py`.

### № 39. Эффект кармы «+15 % к лечению» у Благочестивых
**Статус:** ✅ сделано. **Доказательство:** обещан текстом `karma_status` («+15% к лечению»), реализован не был; теперь `bot/handlers/inventory.py` (use_item) и `engine/inventory.use` умножают heal на `1 + HEAL_BONUS` при `pious()`.
**Проверка:** `tests/test_karma_omens_engine.py`, `run_all.py`.

### № 40. Эффект кармы «+20 % к урону Тьмы» у Осквернителей
**Статус:** ✅ сделано. **Доказательство:** `bot/handlers/battle.py:combat_skill` (школа `shadow` из `best_affinity`) и `engine/combat.py` (action `skill`, школа `shadow` в `p.magic`) умножают урон на `1 + DARK_DAMAGE_BONUS` при `defiled()`.
**Проверка:** `tests/test_karma_omens_engine.py` (константы и паритет), `run_all.py`.

### № 41. Кнопка «🔮 Знамения» в меню бота
**Статус:** ✅ сделано. **Доказательство:** кнопка в `bot/keyboards/inline.py:main_menu_keyboard` (callback `omens_menu`) + хендлер `bot/handlers/world_extra.py:omens_menu`, экран собирается из `core/omens.py` (каталог — `engine/omens.py`, один на оба стека).
**Проверка:** `tests/test_omens_and_gathering.py`, `run_all.py`.

### № 42. Экран «🔮 Знамения» в браузерном движке
**Статус:** ✅ сделано. **Доказательство:** `engine/game.py:do_omens` + кнопка в `menu()`; текст — `engine/omens.omens_text`.
**Проверка:** `tests/test_karma_omens_engine.py`.

### № 43. Реактивные диалоги NPC в боте
**Статус:** ✅ сделано. **Доказательство:** было — `core/dialogue.py` не вызывался, в `talk_npc` показывался только статичный `cell.npc_dialogue`; стало — `bot/handlers/location.py:talk_npc` при активном катаклизме/осаде/караване (`core/worldevents.active_cataclysms/active_sieges/active_caravans`) отдаёт `generate_reactive_dialogue`; пороги кармы берутся из `core/karma.py` (дубликат ±150 из диалогов удалён).
**Проверка:** `run_all.py` (тесты лора), `tests/test_lore_and_legends.py`.

### № 44. Строка кармы в профиле героя (оба стека)
**Статус:** ✅ сделано. **Доказательство:** `bot/utils/texts.py:profile_text` и `engine/texts.py:profile` выводят `karma_line` (значок, число, титул) из `core/karma.py` / `engine/karma.py`.
**Проверка:** `tests/test_karma_omens_engine.py`, `run_all.py`.

### № 45. Археология: вход игроку в боте
**Статус:** ✅ сделано. **Доказательство:** было — `core/archaeology.py` вызывался только тестами.
**Сделано:** кнопка «⛏ Копать землю (Археология)» на клетке вне города (`inspect_keyboard`, флаг `can_dig`) + хендлер `dig_relic`; счётчик «🔍 Фрагментов скрижали: N/5» в осмотре; при совпадении клетки с картой — «🏆 Выкопать клад по карте!» (`has_treasure`) и хендлер `dig_treasure`, который тратит карту и выдаёт награду.
**Файлы:** `bot/handlers/location.py`, `bot/keyboards/inline.py`.
**Проверка:** `tests/test_bot_entrypoints.py::test_archaeology_flow_gives_map_and_treasure` (включая промах по координатам).

### № 46. Инвестиции: вход игроку в боте + выплата дивидендов
**Статус:** ✅ сделано. **Доказательство:** вклады принимались только из тестов, а выплат не существовало вовсе: колонка `earned_dividends` никогда не росла.
**Сделано:** кнопка «🏦 Вклад в лавку» в безопасной локации + экран `invest_menu` (капитал лавки, своя доля в %, полученные дивиденды) и вклад фиксированными суммами `INVEST_STEPS = (100, 500, 2000)` с защитой от подделанного колбэка; в `core/investments.py` добавлена `pay_dividends()` (`DIVIDEND_RATE = 0.02` в сутки, `selectinload` вместо ленивых связей); в `bot/runner.py` — цикл `_dividend_loop` с корректной остановкой задачи и личным уведомлением вкладчику.
**Файлы:** `bot/handlers/location.py`, `bot/keyboards/inline.py`, `bot/runner.py`, `core/investments.py`.
**Проверка:** `tests/test_bot_entrypoints.py::test_investment_dividends_are_paid`.

### № 47. Ломбард: вход игроку в боте
**Статус:** ✅ сделано (кроме перетекания просрочки на рынок — см. № 48).
**Сделано:** кнопка «⚫️ 💍 Заложить» в карточке именной вещи (`item_book_keyboard`, флаг `can_pawn`; надетую и спрятанную заложить нельзя) + хендлер `pawn:`; экран «💍 Ломбард» в городе (`pawnshop_menu`) со списком активных займов, ценой выкупа и кнопками `pawn_redeem:`.
**Файлы:** `bot/handlers/inventory.py`, `bot/keyboards/inline.py`.
**Проверка:** `tests/test_bot_entrypoints.py::test_pawnshop_loan_and_redeem_roundtrip` (вещь уходит из сумки, выкуп возвращает её и списывает комиссию).

### № 48. Чёрный рынок: витрина для игроков
**Статус:** 🟡 частично. **Сделано:** кнопка «🕯 Чёрный рынок» в городе + экран `blackmarket_menu` с витриной из `core/blackmarket.BLACK_MARKET_WARES` (кнопка покупки появляется только при достаточных средствах) и хендлер `bm_buy:`.
**Остаток:** просроченные залоги из № 47 пока не перетекают в витрину — нужен sweep просрочки (`is_liquidated`) в фоновом цикле `bot/runner.py` и добавление ликвидированных вещей в ассортимент.
**Файлы:** `bot/handlers/location.py`, `bot/keyboards/inline.py`.
**Проверка:** `tests/test_bot_entrypoints.py::test_blackmarket_purchase_requires_money`.

### № 49. Фазы луны: показ игроку в боте
**Статус:** 🟡 частично. **Сделано:** строка текущей фазы и её эффекта выводится при осмотре клетки (`inspect_cell` → `core/lunar.get_current_lunar_phase`).
**Остаток:** множители фазы (`mob_mult`, `material_mult`, `magic_dark_mult`) пока нигде не применяются к спавну/дропу/магии — их нужно подключить в `core/spawns.py`, `core/loot.py` и `bot/handlers/battle.py:combat_skill`.
**Файлы:** `bot/handlers/location.py`.
**Проверка:** `tests/test_bot_entrypoints.py::test_lunar_phase_is_deterministic_and_covers_cycle`.

### № 50. Разбор вещей на материалы в боте
**Статус:** ✅ сделано. **Сделано:** кнопка «🟠 🔧 Разобрать» в карточке снаряжения (`item_book_keyboard`, флаг `can_salvage`; надетую вещь разобрать нельзя) + хендлер `salvage:` — вызывает `core/salvage.salvage_item` и показывает выход материалов (лом, слитки, магическая пыль).
**Файлы:** `bot/handlers/inventory.py`, `bot/keyboards/inline.py`.
**Проверка:** `tests/test_bot_entrypoints.py::test_item_book_keyboard_has_salvage_and_pawn`, `test_handlers_registered`.

### № 51. Гильдии: вход игроку в боте
**Статус:** ⬜ не сделано. **Доказательство:** `core/guilds.py` — импорт только из `tests/test_guilds_and_mentorship.py`.
**ТЗ:** меню «🏛 Гильдия» в главном меню; создание/вступление/роли через функции `core/guilds.py`; список участников; событие в `core/realtime.py`.
**Файлы:** `bot/keyboards/inline.py`, `bot/handlers/party.py` или новый `bot/handlers/guilds.py` (+ роутер в `__init__.py`).

### № 52. Наставничество: вход игроку в боте
**Статус:** ⬜ не сделано. **Доказательство:** `core/mentorship.py` — импорт только из `tests/test_guilds_and_mentorship.py`.
**ТЗ:** приглашение наставника/ученика из профиля (`bot/handlers/character.py`); бонус опыта применяется в `bot/handlers/battle.py:_finish_victory` (если связка активна).
**Файлы:** `bot/handlers/character.py`, `bot/handlers/battle.py`, `bot/keyboards/inline.py`.

### № 53. Дуэли: вызов другого игрока на клетке
**Статус:** ⬜ не сделано. **Доказательство:** `core/duels.py` — импорт только из `tests/test_guilds_and_mentorship.py`; в `bot/handlers/location.py` есть показ «здесь же стоят другие герои», но взаимодействия с ними нет (кроме отряда).
**ТЗ:** кнопка «⚔ Дуэль» в списке героев на клетке; подтверждение обеими сторонами; бой через `core/duels.py` (готовые функции); итог — сообщение обоим.
**Файлы:** `bot/handlers/location.py`, `bot/keyboards/inline.py`.

### № 54. Престиж: перерождение после капа в боте
**Статус:** ⬜ не сделано. **Доказательство:** `core/prestige.py` — импорт только из `tests/test_progression_and_karma.py`; пункт 5 `IDEAS-next.md` не закрыт.
**ТЗ:** кнопка «♻ Престиж» в профиле при максимальном уровне; сброс уровня и выдача постоянного бонуса через `core/prestige.py`; титул престижа в `profile_text`.
**Файлы:** `bot/handlers/character.py`, `bot/utils/texts.py`, `bot/keyboards/inline.py`.

### № 55. Доска наград за головы в боте
**Статус:** ⬜ не сделано. **Доказательство:** `core/bounty.py` — импорт только из `tests/test_omens_and_gathering.py`.
**ТЗ:** экран «💰 Награды» в меню; заказы на тварей из `core/bounty.py`; закрытие заказа в `bot/handlers/battle.py:_finish_victory`.
**Файлы:** `bot/keyboards/inline.py`, `bot/handlers/world_extra.py` (или новый хендлер), `bot/handlers/battle.py`.

### № 56. Иллюзии: применение игроком в боте
**Статус:** ⬜ не сделано. **Доказательство:** `core/illusions.py` — импорт только из `tests/test_lore_and_legends.py`.
**ТЗ:** экран иллюзий у мага (`bot/handlers/character.py`, рядом с фамильярами); применение — через функции `core/illusions.py`; эффект отображается в экране клетки.
**Файлы:** `bot/handlers/character.py`, `bot/keyboards/inline.py`.

### № 57. Бестиарий: записи об убитых тварях в боте
**Статус:** ⬜ не сделано. **Доказательство:** `core/bestiary.py` — импорт только из `tests/test_lore_and_legends.py`; статистика боёв в БД есть (модель `Battle`).
**ТЗ:** кнопка «📖 Бестиарий» в профиле; записи по видам из `Battle`/`core/bestiary.py`; картинки — `core/mob_images.py` (уже подключён в бою).
**Файлы:** `bot/handlers/character.py`, `bot/keyboards/inline.py`, `core/bestiary.py`.

### № 58. Питомцы: вход игроку в боте (сейчас — только админка)
**Статус:** ⬜ не сделано. **Доказательство:** `core/pets.py` импортируется только `admin/main.py`; игроку питомцы недоступны, хотя шаблоны редактируются в `editor_pets.html`.
**ТЗ:** экран питомца в профиле; выбор/кормление через функции `core/pets.py`; пассивный бонус питомца — в `core/stats.py` (там уже подключаются подклассы/таланты — тот же паттерн).
**Файлы:** `bot/handlers/character.py`, `bot/keyboards/inline.py`, `core/stats.py`.

### № 59. `core/auction_bid.py` — мёртвый модуль: дописать или удалить
**Статус:** ⬜ не сделано (требует решения). **Доказательство:** файл содержит одну константу `BID_AUCTION_KEY = "bid_auction"` и **не импортируется нигде**, включая тесты (AST-анализ). Комментарий заявляет «Аукцион со ставками (для предметов админа)».
**ТЗ (на выбор, решение зафиксировать в README/комментарии):** (а) удалить файл, если ставки не планируются; (б) дописать систему ставок: `core/auction_bid.py` + хендлер в `bot/handlers/auction.py` + тест. Если (а) — проверить `git grep BID_AUCTION_KEY` перед удалением.
**Файлы:** `core/auction_bid.py`, при (б) — `bot/handlers/auction.py`, `tests/`.

### № 60. Летопись рекордов (`ServerRecord`) — показать игрокам
**Статус:** ⬜ не сделано. **Доказательство:** модель `ServerRecord` (`core/models.py`) читается только в `core/legends.py`; в боте экрана летописи нет.
**ТЗ:** кнопка «📖 Летопись» в меню; экран из `core/legends.py` (записи «первый босс», «крупнейший катаклизм»); запись новых рекордов — в местах, где события уже завершаются (`core/worldevents.py`, `core/dungeons.py`).
**Файлы:** `bot/keyboards/inline.py`, `bot/handlers/world_extra.py`, `core/legends.py`.

## Раздел 4. Админка `admin/main.py`: 13 подсистем невидимы для владельца (№ 61–70)

> **Общее доказательство для раздела.** Grep 2026-08-14 по `admin/main.py`: **0 вхождений** слов `invest`, `pawnshop`, `lunar`, `salvage`, `guild`, `mentor`, `duel`, `bounty`, `prestige`, `archaeo`, `omens`, `karma`, `blackmarket`. Игроки и владелец играют в невидимые механики.
> **Общий шаблон ТЗ:** (1) страница/секция в существующем шаблоне (`admin/templates/*.html`); (2) роут в `admin/main.py` в стиле соседних (`@app.get(...)` + `TemplateResponse`); (3) для изменяемых данных — POST-форма с валидацией (паттерн фикса «мусор в числовых полях», `AUDIT-BUGS.md` п. 19); (4) запись в журнал аудита (`admin/main.py` уже ведёт логи). **Приёмка:** `tests/test_ui_images.py::test_admin_routes` расширен новыми маршрутами и зелёный; страница открывается TestClient'ом.

### № 61. Админка: карма в карточке игрока
**Статус:** ⬜ не сделано. **Доказательство:** колонка `karma_score` (`core/models.py:308`); в `admin/templates/player_detail.html` поля кармы нет.
**ТЗ:** показ `⚖️ Карма: N (титул из core/karma.karma_status)` в `player_detail.html`; POST `/player/{id}/set-karma` (диапазон −500..500, валидация числа); запись в аудит.
**Файлы:** `admin/main.py`, `admin/templates/player_detail.html`.

### № 62. Админка: ломбард (займы `PawnLoan`)
**Статус:** ⬜ не сделано. **Доказательство:** модель `PawnLoan` (`core/models.py:1329` `loan_bronze`); страницы нет.
**ТЗ:** страница `/pawnshop`: список активных и просроченных займов (кто, сумма, залог, срок), действие «списать просроченный залог».
**Файлы:** `admin/main.py`, `admin/templates/pawnshop.html` (новый), пункт меню в `admin/templates/base.html`.

### № 63. Админка: инвестиции (`TownInvestment`)
**Статус:** ⬜ не сделано. **Доказательство:** модель `TownInvestment` (`core/models.py:1313`); страницы нет.
**ТЗ:** секция в `/settings` или страница `/investments`: суммарные вклады по локациям, ручная выплата дивидендов (кнопка с подтверждением).
**Файлы:** `admin/main.py`, `admin/templates/settings.html` или новый шаблон.

### № 64. Админка: чёрный рынок
**Статус:** ⬜ не сделано. **Доказательство:** `core/blackmarket.py` не упоминается в `admin/main.py`.
**ТЗ:** страница `/blackmarket`: текущая витрина, добавление/снятие лотов, просмотр источника лота (залог/админ).
**Файлы:** `admin/main.py`, `admin/templates/blackmarket.html` (новый).

### № 65. Админка: фазы луны
**Статус:** ⬜ не сделано. **Доказательство:** `core/lunar.py` не упоминается в `admin/main.py`.
**ТЗ:** блок «🌙 Фаза луны» на `/dashboard` (текущая фаза, эффекты, до смены фазы); принудительная смена фазы — кнопка с аудитом.
**Файлы:** `admin/main.py`, `admin/templates/dashboard.html`.

### № 66. Админка: гильдии и наставничество
**Статус:** ⬜ не сделано. **Доказательство:** `core/guilds.py`, `core/mentorship.py` не упоминаются в `admin/main.py`.
**ТЗ:** страница `/guilds`: список гильдий (участники, глава), роспуск; связки наставников — на той же странице.
**Файлы:** `admin/main.py`, `admin/templates/guilds.html` (новый).

### № 67. Админка: дуэли и арена
**Статус:** ⬜ не сделано. **Доказательство:** `core/duels.py`, `core/arena.py` не упоминаются в `admin/main.py`; тени `CharacterShadow` существуют (`core/models.py`).
**ТЗ:** секция «⚔ Арена» на `/battles`: активные дуэли, рекорды арены, ручная отмена зависшей дуэли.
**Файлы:** `admin/main.py`, `admin/templates/battles.html`.

### № 68. Админка: редактор знамений
**Статус:** ⬜ не сделано. **Доказательство:** каталог знамений теперь в `engine/omens.py` (один на оба стека); в админке редактора нет.
**ТЗ:** страница `/omens`: список знамений, добавление/удаление; запись в `AppSetting` (настройки), чтение — `core/omens.get_current_omens` расширяется на динамику из настроек; предпросмотр `omen_banner()`.
**Файлы:** `admin/main.py`, `admin/templates/editor_omens.html` (новый), `core/omens.py`.

### № 69. Админка: престиж, титулы, подклассы, таланты
**Статус:** ⬜ не сделано. **Доказательство:** `core/prestige.py`, `core/titles.py`, `core/subclasses.py`, `core/talents.py` не упоминаются в `admin/main.py` (только `core/stats.py` их применяет).
**ТЗ:** просмотр в карточке игрока: престиж, титул, подкласс, выбранные таланты (read-only список + сброс талантов одной кнопкой).
**Файлы:** `admin/main.py`, `admin/templates/player_detail.html`.

### № 70. Realtime-лента: события новых подсистем
**Статус:** ⬜ не сделано. **Доказательство:** `core/realtime.py` публикует `player_move`, `battle_result`, `auction_new` и т. д. (см. docstring модуля); события кармы/знамений/ломбарда/инвестиций не публикуются.
**ТЗ:** добавить `publish` в местах из № 36–48 (карма изменилась, знамение показано, залог оформлен, дивиденды выплачены) с теми же полями, что у соседних событий; в `admin/templates/dashboard.html` — фильтр ленты по новым типам.
**Файлы:** `bot/handlers/*`, `core/realtime.py`, `admin/main.py`, `admin/templates/dashboard.html`.

---

## Раздел 5. Браузерная панель `webapp/pages/` — Pyodide-сторона (№ 71–76)

> **Общее доказательство.** `webapp/pages/` содержит `dashboard, bot, players, dungeons, world_*, content, economy, audit, settings, updates, code`; страниц для подсистем из Раздела 2 нет — после их переноса панель должна их показывать. Модули подключаются через `modules.json` + боковое меню (стережёт `tests/test_wiring.py`).
> **Приёмка у всех пунктов:** `python3 tools/build_bundle.py`, `python3 tests/test_wiring.py` зелёный, страница открывается в Pyodide-панели без ошибок консоли.

### № 71. `webapp/pages/economy.py`: инвестиции, ломбард, чёрный рынок
**Статус:** ⬜ не сделано (ждёт № 13–15). **ТЗ:** вкладки существующей страницы экономики: вклады по локациям, активные займы, витрина рынка — данные из `engine/investments.py`, `engine/pawnshop.py`, `engine/blackmarket.py`.
**Файлы:** `webapp/pages/economy.py`, `webapp/actions/economy_actions.py`.

### № 72. `webapp/pages/world_living.py`: знамения и фазы луны
**Статус:** 🟡 частично (знамения в движке есть, страницы нет). **ТЗ:** блок «🔮 Знамения» (список + баннер `engine/omens.omen_banner`) и «🌙 Луна» (фаза из `engine/lunar.py` после № 16).
**Файлы:** `webapp/pages/world_living.py`.

### № 73. `webapp/pages/players.py`: карма в профиле игрока
**Статус:** ⬜ не сделано. **Доказательство:** `engine/models.py:Player.karma_score` добавлен; в `webapp/pages/players.py` поля нет.
**ТЗ:** строка кармы (титул из `engine/karma.karma_status`) в карточке игрока + поле правки кармы для админа.
**Файлы:** `webapp/pages/players.py`, `webapp/actions/player_actions.py`.

### № 74. `webapp/pages/content.py`: питомцы и фамильяры
**Статус:** ⬜ не сделано (ждёт № 19–20). **ТЗ:** редактор шаблонов питомцев (паритет с `admin/templates/editor_pets.html`) и просмотр фамильяров игроков.
**Файлы:** `webapp/pages/content.py`, `webapp/actions/content_actions.py`.

### № 75. `webapp/pages/dungeons.py`: археология и карты сокровищ
**Статус:** ⬜ не сделано (ждёт № 11). **ТЗ:** просмотр фрагментов скрижалей и координат карт сокровищ игроков; на карте мира (`world_map.py`) — метка тайника.
**Файлы:** `webapp/pages/dungeons.py`, `webapp/pages/world_map.py`.

### № 76. `webapp/pages/`: бестиарий в панели
**Статус:** ⬜ не сделано (ждёт № 32). **ТЗ:** страница бестиария: справочник тварей из `engine/content.py:MOBS` + счётчики убийств по серверу.
**Файлы:** `webapp/pages/content.py` (или новая страница + меню).

---

## Раздел 6. Известные баги и незакрытые долги из `AUDIT-BUGS.md` (№ 77–88)

> Каждый пункт ссылается на конкретный пункт `AUDIT-BUGS.md` — это собственный бэклог проекта, не выдумка.

### № 77. `player.worn` — именные статы в браузерном бою (долг B)
**Статус:** ✅ сделано (основная часть). **Доказательство:** было — `engine/rules.py:24` читал `worn`, но никто не писал (долг B, `AUDIT-BUGS.md`); стало — `engine/inventory.py:equip/unequip/sell/toss` пишут/чистят `worn`, `engine/items.resolve_owned` выбирает экземпляр, бой берёт статы через `rules.stats(p, store)` (`engine/combat.py`, `engine/worldboss.py`).
**Остаток (отдельный пункт):** пути, где экипировка снимается без `inventory.py` (смерть/карман) — закрываются вместе с № 79–80.
**Проверка:** `tests/test_karma_omens_engine.py` («в бою статы экземпляра: 37 = 37»).

### № 78. Могила хранит этаж гибели в браузерном стеке (зеркало фикса № 17)
**Статус:** ✅ сделано. **Доказательство:** `engine/death.bury/at/keys/claim/grave_card` теперь работают с `floor`; регрессия в `tests/test_karma_omens_engine.py` («на поверхности могилы из подземелья нет», «ключ карты учитывает этаж»).
**Проверка:** `python3 tests/test_karma_omens_engine.py`.

### № 79. Инвентарь по uid экземпляров вместо индексов шаблонов (долг A)
**Статус:** ⬜ не сделано (главный рефакторинг). **Доказательство:** `AUDIT-BUGS.md`, раздел «A. Идентичность предмета = индекс шаблона»: `p.inventory` хранит индексы; продажа/прятание второй копии надетой вещи снимает экипировку; дубликат надетой вещи не выпадает в могилу (`engine/stash.drop_on_death` считает «надетым» по индексу).
**ТЗ:** перевести `p.inventory`/`p.equipped` на uid экземпляров с обратной совместимостью (миграция старых сохранений: индекс → `items.create` или заглушка-экземпляр); затронуть `engine/inventory.py`, `engine/shop.py`, `engine/stash.py`, `engine/death.py`, `engine/trade.py`, `engine/texts.py`, `engine/itemui.py`, `engine/auction.py`; после — убрать `resolve_owned`-эвристику из № 77 (она станет не нужна).
**Критерий приёмки:** два одинаковых меча: продажа одного не снимает второй; смерть роняет только ненадетые копии; старые сейвы открываются и конвертируются.
**Что НЕ делать:** не менять формат данных серверного стека — рефакторинг только `engine/`.

### № 80. `stash.drop_on_death` по uid (после № 79)
**Статус:** ⬜ не сделано (зависит от № 79). **Доказательство:** `engine/stash.py:216-217` — `worn = set(p.equipped.values())`, `losable = [i for i, idx in enumerate(p.inventory) if idx not in worn]` — сравнение по индексу, отсюда «иммунитет к потере при смерти» для дубликатов.
**ТЗ:** после перевода инвентаря на uid сравнивать uid надетых экземпляров; регрессия: игрок с двумя одинаковыми мечами, один надет — при смерти теряется ненадетый.
**Файлы:** `engine/stash.py`, `tests/test_stash.py` (расширить).

### № 81. Аукцион: сироты при удалённом продавце
**Статус:** ⬜ не сделано. **Доказательство:** `AUDIT-BUGS.md`, раздел C: «`core/auction._return_to_owner` при удалённом продавце создаёт `InventoryItem` на несуществующего персонажа (сирота)».
**ТЗ:** если владелец удалён — вещь уходит скупщику (как при истечении лота), а не создаёт запись с `character_id` мертвеца; тест: удалить продавца → `_return_to_owner` → записи-сироты нет.
**Файлы:** `core/auction.py`, `tests/test_bugfixes.py` (расширить).

### № 82. Скупщик: лоты исчезают через 72 ч вопреки документации
**Статус:** ⬜ не сделано. **Доказательство:** `AUDIT-BUGS.md`, раздел C: «Лоты скупщика: через 72 ч вещь с витрины исчезает из мира совсем — противоречит документации "предмет не исчезает из мира"».
**ТЗ:** выбрать политику и реализовать одну: (а) вещь остаётся на витрине бессрочно, (б) вещь уходит в реестр бесхозных экземпляров. Исправить документацию под выбранную политику; тест на оба исхода.
**Файлы:** `core/auction.py`, README/комментарии, `tests/test_bugfixes.py`.

### № 83. `ADMIN_SECRET_KEY` — обязательный env вместо дефолта
**Статус:** ⬜ не сделано. **Доказательство:** `AUDIT-BUGS.md`, раздел C: `admin/auth.py` содержит дефолт `ADMIN_SECRET_KEY = "shadow-lands-secret"` — при выставлении панели наружу это отсутствие авторизации.
**ТЗ:** если переменная окружения не задана — при старте панели либо генерация случайного ключа с выводом в лог, либо отказ с понятной ошибкой (выбрать одно и зафиксировать в README); тест: без env панель не принимает дефолтный пароль.
**Файлы:** `admin/auth.py`, `launch.py`, `README.md`, `tests/test_access.py` (расширить).

### № 84. Колбэки «по позиции» → id в `callback_data`
**Статус:** ⬜ не сделано. **Доказательство:** `AUDIT-BUGS.md`, раздел C: «Колбэки "по позиции" (продажа из старого сообщения) могут сработать на сдвинувшемся списке… полноценно лечится id в callback_data».
**ТЗ:** в продаже/использовании из инвентаря бота передавать `inv_item.id` вместо индекса в списке; сервер проверяет принадлежность вещи игроку; тест: два сообщения инвентаря, продажа из старого не трогает чужой слот.
**Файлы:** `bot/handlers/inventory.py`, `bot/keyboards/inline.py`, `tests/test_bugfixes.py`.

### № 85. Карма: «защита от фатального удара» у Благочестивых
**Статус:** ✅ сделано. **Доказательство:** эффект был обещан текстом `karma_status`, но не существовал ни в одном стеке.
**Сделано:** `_blessing_saves()` в обоих стеках — при HP ≤ 0 у Благочестивого один раз за бой остаётся 1 HP, флаг траты живёт в состоянии боя. В боте прикрыты **все три** точки смерти (атака, защита, умение), в движке — и обычный удар, и смерть от засады; в лог движка пишется «✨ Благословение света спасло тебя!».
**Файлы:** `bot/handlers/battle.py`, `engine/combat.py`.
**Проверка:** `tests/test_karma_omens_engine.py` (4 проверки) и `tests/test_bot_entrypoints.py::test_karma_effects_in_bot_helpers`.

### № 86. Знамения ↔ катаклизмы: привязка предвестников к реальным бедствиям
**Статус:** ⬜ не сделано. **Доказательство:** `engine/omens.py` — статичный список (`get_current_omens` возвращает весь каталог); `core/worldevents.py:active_cataclysms` существует.
**ТЗ:** за N часов до авто-катаклизма (таймеры уже в `engine/cataclysm.py` / `core/worldevents.py`) активное знамение = соответствующее бедствию (маппинг «вид бедствия → знамение» завести в `engine/omens.py`); в спокойное время — случайный баннер без привязки; тест: создаётся бедствие → `get_current_omens()` содержит его знамение.
**Файлы:** `engine/omens.py`, `engine/cataclysm.py`, `core/omens.py`, `core/worldevents.py`, `tests/test_omens_and_gathering.py` (расширить).

### № 87. Задания: выдача и сдача в боте (долг реестра паритета)
**Статус:** ⬜ не сделано. **Доказательство:** `tests/test_parity.py` REGISTRY: Feature «Задания» с `todo="на сервере есть модель Quest, но нет выдачи и сдачи в боте"`; в движке задания работают (`engine/quests.py`), на сервере — только таблицы (`core/models.py`: `Quest`, `CharacterQuest`).
**ТЗ:** NPC-квестодатели (данные уже в `core/seed_content.py`); выдача (создание `CharacterQuest`) и сдача (`bot/handlers/…` + прогресс в `bot/handlers/battle.py:_finish_victory`); после — убрать `todo` из реестра.
**Файлы:** `bot/handlers/location.py` (или новый `bot/handlers/quests.py` + роутер), `bot/handlers/battle.py`, `tests/test_parity.py`.

### № 88. Миграция старых сохранений движка под новые поля Player
**Статус:** ✅ сделано. **Сделано:** регрессия в `tests/test_karma_omens_engine.py` — старый словарь сейва без новых ключей открывается, `bronze/silver/karma_score` получают 0, старые поля (имя, золото) сохраняются, `to_dict`/`from_dict` работают без потерь.
**Проверка:** `python3 tests/test_karma_omens_engine.py` (раздел «Старые сохранения открываются под новые поля»).

## Раздел 7. Трёхвалютная экономика — единственный долг паритета (№ 89–94)

> **Общее доказательство.** `tests/test_parity.py` REGISTRY: Feature «Трёхвалютная экономика» — `browser=["engine/currency.py"], server=[], todo=...`. Колонки есть у обеих моделей: `core/models.py:215-216` (`bronze`, `silver` у `Character`), `engine/models.py` (`bronze`, `silver` у `Player` — добавлены в этой сессии). Конвертация 1:100 реализована в `engine/currency.py` (`CONVERSION = 100`), и сервер уже тратит/начисляет бронзу через `add_currency`/`deduct_currency` (примеры: `bot/handlers/character.py:familiar_adopt_handler`, `core/investments.py:invest_in_town`). Не сделано: **движок всё ещё начисляет и тратит единый `gold`**.

### № 89. Поля `bronze`/`silver` у `Player` и кошелёк в профиле
**Статус:** ✅ сделано. **Доказательство:** `engine/models.py` — поля добавлены; `engine/texts.py:profile` показывает `currency_str(p)` («0🟤 0⚪ 50🟡»).
**Проверка:** `tests/test_karma_omens_engine.py` («профиль показывает три валюты»).

### № 90. Движок: начисления через `add_currency`
**Статус:** ⬜ не сделано. **Доказательство:** `engine/combat.py:_reward` — `p.gold += gold`; `engine/worldboss.py:_reward_all` — `p.gold += gold`; `engine/death.py:claim` — `p.gold += taken`; `engine/inventory.py:sell` — `p.gold += paid`. Механика начисления «золота» в обход конвертации.
**ТЗ:** заменить все `p.gold += N` (grep: `grep -rn "gold += " engine/`) на `currency.add_currency(p, gold=N)` (эквивалентно по числу, т. к. нормализация не дробит золото вниз); добавить в `engine/currency.py` docstring-таблицу «какие функции каким путём меняют кошелёк».
**Файлы:** `engine/combat.py`, `engine/worldboss.py`, `engine/death.py`, `engine/inventory.py`, `engine/shop.py`, `engine/auction.py`, `engine/quests.py`, `engine/party.py` (по grep).
**Критерий приёмки:** `grep -rn "gold += " engine/` пуст; все существующие тесты движка зелёные (суммы не изменились).

### № 91. Движок: цены и траты через `deduct_currency`
**Статус:** ⬜ не сделано. **Доказательство:** покупки в `engine/shop.py`, `engine/auction.py`, `engine/merchant.py` вычитают из `p.gold` напрямую; `engine/currency.deduct_currency(p, cost_bronze)` существует и не используется движком.
**ТЗ:** ценники хранить в бронзе (как сервер: `Item.price` — в бронзе); списание через `deduct_currency` с понятной ошибкой «Не хватает N🟤» (текст уже используется сервером в `core/investments.py`); проверить `itemui.resale_of` и скупку.
**Файлы:** `engine/shop.py`, `engine/auction.py`, `engine/merchant.py`, `engine/craft.py`, `engine/itemui.py`.
**Критерий приёмки:** сценарий «0 золота, 150 бронзы, зелье за 1 золото»: в старом коде — отказ, в новом — покупка возможна только после конвертации; тест на границу конвертации (99🟤 → 100🟤).

### № 92. Бот: единая точка списания (добить остатки прямых `gold`)
**Статус:** 🟡 частично. **Доказательство:** часть бота уже тратит через `deduct_currency` (фамильяры, инвестиции), но есть прямые обращения к `gold`/`bronze` в хендлерах (найти: `grep -rn "\.gold \|bronze" bot/handlers/`).
**ТЗ:** пройти по grep-результату и перевести все траты/начисления на `engine/currency.add_currency`/`deduct_currency`; в `profile_text` кошелёк уже показывается тремя валютами (`bot/utils/texts.py`, `currency_str`).
**Файлы:** по grep-результату.
**Критерий приёмки:** в боте не осталось прямых `character.gold += / -=`; pytest-сценарии экономики зелёные.

### № 93. Сквозной тест конвертации 1:100 в обоих стеках
**Статус:** ⬜ не сделано. **Доказательство:** `engine/currency.py` имеет собственные тесты? — нет отдельного набора; серверная конвертация покрыта косвенно (`tests/test_economy_and_lunar.py`).
**ТЗ:** pytest-набор `tests/test_currency_parity.py`: (1) `add_currency` 99+1 бронзы → 0🟤 1⚪; (2) 9999+1 → 0🟤 0⚪ 1🟡; (3) `deduct_currency` по частям из трёх валют; (4) один и тот же сценарий прогоняется для `Player` (движок) и для `Character` (сервер, in-memory SQLite) и даёт одинаковые строки `currency_str`.
**Файлы:** `tests/test_currency_parity.py` (новый, попадёт в автодетект `run_all.py`).

### № 94. Снять долг «Трёхвалютная экономика» с реестра
**Статус:** ⬜ не сделано (зависит от № 90–93). **ТЗ:** после закрытия 90–93 обновить `REGISTRY` в `tests/test_parity.py`: `server=["core/models.py", "core/…"]` (по факту реализации) и `todo=""`.
**Критерий приёмки:** `python3 tests/test_parity.py` печатает «Паритет: 27 из 27 механик в обоих стеках» и пустой список «Ждут переноса».
**Что НЕ делать:** не стирать `todo` раньше № 90–93 — реестр обязан быть честным.

---

## Раздел 8. Документация и метаданные (№ 95–100)

### № 95. `IDEAS-next.md`: актуальное число паритета
**Статус:** ✅ сделано. **Доказательство:** было «Сейчас 20 из 20 механик в обоих стеках» — устарело (реестр вырос до 27 записей); стало «26 из 27 механик в обоих стеках (долг — трёхвалютная экономика)» + упоминание кармы/знамений.
**Проверка:** `grep -n "26 из 27" IDEAS-next.md`.

### № 96. `README.md`: список модулей `engine/` и описание тестов
**Статус:** ⬜ не сделано. **Доказательство:** в `README.md` раздел «Структура» перечисляет `engine/*.py`, но `karma.py` и `omens.py` (добавлены в этой сессии) не упомянуты; раздел о тестах не описывает новый автодетект `run_all.py`.
**ТЗ:** добавить в список `karma.py` («карма: пороги ±150, поступки и эффекты — паритет с core/karma.py») и `omens.py` («знамения: единый каталог для обоих стеков»); в раздел про тесты — что `run_all.py` запускает все `tests/test_*.py` (pytest-наборы — через pytest) и требует `pip install -r requirements.txt pytest pytest-asyncio`.
**Файлы:** `README.md`.
**Критерий приёмки:** `grep -n "karma.py" README.md` не пуст; инструкция в README воспроизводима на чистой машине.

### № 97. `README.md`: таблица «как запускать проверки»
**Статус:** ⬜ не сделано. **Доказательство:** команды разбросаны (`python3 tests/run_all.py`, `python3 tools/build_bundle.py`, `python3 tests/test_parity.py`); единой таблицы нет.
**ТЗ:** в README таблица: «все тесты», «только паритет», «пересборка бандла после правки engine/webapp», «один набор», с ожидаемым результатом каждой команды.
**Файлы:** `README.md`.

### № 98. `AUDIT-BUGS.md`: отметить закрытые долги B и C
**Статус:** ⬜ не сделано. **Доказательство:** долги «B. player.worn» и «C. engine/death.bury без этажа» закрыты в этой сессии, но в `AUDIT-BUGS.md` они всё ещё значатся открытыми.
**ТЗ:** добавить в `AUDIT-BUGS.md` датированную запись «2026-08-14»: B закрыт (файлы, тест), C закрыт (файлы, тест); A остаётся открытым (см. IDEAS-100.md № 79–80).
**Файлы:** `AUDIT-BUGS.md`.

### № 99. `IDEAS-next.md`: статусы пунктов 2–10 по факту кода
**Статус:** ⬜ не сделано. **Доказательство:** пункт 3 «Дуэли и арена» числится без статуса, хотя `core/arena.py` уже подключён к боту (`bot/handlers/world_extra.py:arena_menu_handler`) и есть тест `tests/test_dungeon_and_arena.py`; пункт 2 «Обмен» — `engine/trade.py` есть, но прямого обмена между игроками нет; пункт 5 — есть `core/prestige.py`, но без входа.
**ТЗ:** обновить колонку «Статус» таблицы: точное состояние каждого пункта со ссылками на модули («ядро есть, входа нет» / «подключено» / «нет»); статусы верифицировать grep-ом, как в этом файле.
**Файлы:** `IDEAS-next.md`.

### № 100. Правило ведения этого файла
**Статус:** ✅ принято. **ТЗ:** (1) при закрытии пункта менять «Статус» на ✅ с датой, списком файлов и именем теста — голословные «сделано» запрещены; (2) при обнаружении, что пункт уже реализован в коде, — не удалять молча, а перенести в раздел «Сводка аудита» с пометкой «оказалось реализовано»; (3) новые пробелы добавлять в конец соответствующего раздела, а не в новый документ; (4) числа в пунктах (пороги, цены, таймеры) обязаны совпадать с кодом — при расхождении правится пункт, а не код.
**Критерий приёмки:** ревью диффа этого файла не находит пунктов без доказательства (`путь:строка` или команда).

---

## 📊 Итоговая карта по разделам

| Раздел | Кол-во | ✅ сделано | 🟡 частично | Что это за пробелы |
|---|---|---|---|---|
| 1. Тесты и CI | 10 | № 1, 2, 3, 6, 7, 8, 9, 10 | — | 12 забытых наборов, ложные провалы, нет CI, рассинхрон бандла |
| 2. Паритет `core/` → `engine/` | 25 | — | № 35 | 25 серверных подсистем без браузерного близнеца |
| 3. Вход игроку в боте | 25 | № 36–47, 50 | № 48, 49 | подсистемы без единого вызова из `bot/handlers/` |
| 4. Админка `admin/main.py` | 10 | — | — | 13 подсистем с нулём упоминаний в админке |
| 5. Панель `webapp/pages/` | 6 | — | № 72 | страницы Pyodide-панели после переносов Раздела 2 |
| 6. Баги и долги из аудита | 12 | № 77, 78, 85, 88 | — | долги A/B/C, сироты аукциона, секрет, колбэки, квесты |
| 7. Трёхвалютная экономика | 6 | № 89 | № 92 | единственный долг реестра паритета |
| 8. Документация | 6 | № 95, 100 | — | устаревшие цифры и списки |
| **Итого** | **100** | **29** | **6** | — |

**Сделано на 2026-08-14: 29 пунктов закрыто полностью, 6 частично.**
Закрыты: № 1, 2, 3, 6, 7, 8, 9, 10, 36–47, 50, 77, 78, 85, 88, 89, 95, 100.
Проверка: `python3 tests/run_all.py` → **56 наборов, все зелёные** (было 41 запускаемых из 53 существующих). Новые наборы этой сессии: `tests/test_karma_omens_engine.py` (42 проверки), `tests/test_bot_entrypoints.py` (10 тестов), `tests/test_bundle_integrity.py`.

### Что брать следующим (по стоимости/эффекту)
1. **№ 61–70 (админка)** — владелец до сих пор не видит карму, ломбард, вклады и чёрный рынок, хотя игроки ими уже пользуются.
2. **№ 51–58** — оставшиеся входы в боте: гильдии, наставничество, дуэли, престиж, бестиарий, питомцы.
3. **№ 79–80 (долг A)** — рефакторинг инвентаря на uid: чинит семейство багов с дубликатами вещей.
4. **№ 90–94** — добить трёхвалютную экономику и снять последний долг паритета.
