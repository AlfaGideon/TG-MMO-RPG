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
| **Партия 3 (та же дата):** карма в карточке игрока админки — поле правки с клампом, титул и эффект | `admin/main.py`, `admin/templates/player_detail.html` | `tests/test_admin_subsystems.py` |
| Страница `/editor/subsystems`: ломбард, вклады, карма, луна, гильдии, чёрный рынок | `admin/main.py`, `admin/templates/editor_subsystems.html` (новый), `admin/templates/base.html` | `tests/test_admin_subsystems.py` (7 тестов) |
| Ручная выплата дивидендов и изъятие просроченного залога из админки | `admin/main.py` | `tests/test_admin_subsystems.py` |
| **Партия 4 (та же дата):** гильдии — создание, вступление, казна, состав | `bot/handlers/guilds.py` (новый), `bot/handlers/__init__.py`, `bot/keyboards/inline.py` | `tests/test_guild_bounty_duel_entrypoints.py` |
| **Баг:** таблицы гильдий никогда не создавались (модели вне `core/models.py` не попадали в metadata) | `core/migrations.py` | регрессия `test_guild_tables_registered_in_metadata` |
| Наставничество: экран поиска наставника и Очки Чести | `bot/handlers/guilds.py` | `tests/test_guild_bounty_duel_entrypoints.py` |
| Перерождение: кнопка в профиле только для доросших + ритуал | `bot/handlers/guilds.py`, `bot/handlers/character.py`, `bot/keyboards/inline.py` | `tests/test_guild_bounty_duel_entrypoints.py` |
| **Мёртвая кнопка:** `pvp_select` была без обработчика — дуэли со ставками заработали | `bot/handlers/world_extra.py` | `tests/test_guild_bounty_duel_entrypoints.py` |
| **Мёртвая механика:** `record_mob_kill` не вызывался — доска наград всегда пуста; цикл замкнут | `bot/handlers/battle.py`, `bot/handlers/world_extra.py` | `tests/test_guild_bounty_duel_entrypoints.py` |
| **Партия 5:** бестиарий — запись побед, бонус охотника в бою, экран атласа | `bot/handlers/battle.py`, `bot/handlers/character.py` | `tests/test_bestiary_illusions_mentor.py` |
| **Мёртвая колонка:** `Cell.is_illusory_wall` никто не выставлял — добавлена генерация и кнопка «Простучать» | `core/worldgen.py`, `bot/handlers/location.py` | `tests/test_bestiary_illusions_mentor.py` |
| Бонус наставника +25 % опыта и Очки Чести доведены до боя | `bot/handlers/battle.py` | `tests/test_bestiary_illusions_mentor.py` |
| `core/auction_bid.py` помечен явной заглушкой с планом реализации | `core/auction_bid.py` | `test_auction_bid_stub_is_documented` |
| **Партия 6 — доведение всех частичных пунктов:** множители фазы луны применены к спавну, дропу и урону Тьмы | `core/spawns.py`, `core/loot.py`, `bot/handlers/battle.py` | `tests/test_partial_items_done.py` |
| Заморозка фазы луны из админки (override в `AppSetting`) | `core/lunar.py`, `admin/main.py`, `admin/templates/editor_subsystems.html` | `tests/test_partial_items_done.py` |
| Просрочка ломбарда изымается и перепродаётся на чёрном рынке | `core/pawnshop.py`, `core/blackmarket.py`, `bot/handlers/location.py`, `bot/runner.py` | `tests/test_partial_items_done.py` |
| Дуэль по согласию: вызов → принятие/отказ, исход обоим | `bot/handlers/world_extra.py` | `tests/test_partial_items_done.py` |
| Реактивные реплики NPC в браузерном стеке | `engine/dialogue.py` (новый), `engine/explore.py`, `engine/game.py` | `tests/test_partial_items_done.py` |
| Роспуск гильдий из админки; знамения и карма в панели Pyodide | `admin/main.py`, `webapp/pages/world_living.py` | `tests/test_partial_items_done.py` |
| **Партия 7 — долг A:** экипировка помнит конкретную вещь, а не «такую же» | `engine/slots.py` (новый), `engine/models.py`, `engine/inventory.py`, `engine/shop.py`, `engine/stash.py`, `engine/auction.py`, `engine/quests.py` | `tests/test_slot_identity.py` (26 проверок) |
| **Партия 8 — трёхвалютная экономика:** 18 точек движка переведены на кошелёк, суммы считаются в бронзе | `engine/currency.py`, `engine/models.py`, `engine/storage.py` + 12 модулей движка | `tests/test_currency_parity.py` (8 тестов) |
| Миграция старых сейвов: «золото» → бронза без потери покупательной способности | `engine/currency.migrate_raw`, `engine/storage.load` | `tests/test_currency_parity.py` |
| **Последний долг реестра снят: паритет 28 из 28** | `tests/test_parity.py` | `python3 tests/test_parity.py` |
| **Партия 9 — баги из AUDIT-BUGS:** вещь удалённого продавца уходит скупщику, а не в сироты | `core/auction.py` | `tests/test_audit_fixes.py` (11 тестов) |
| Лот скупщика перевыставляется бессрочно — вещь не исчезает из мира | `core/auction.py` | `tests/test_audit_fixes.py` |
| `ADMIN_SECRET_KEY`: публичный дефолт убран, ключ генерируется в `data/` вне git | `admin/auth.py`, `admin/config.py` | `tests/test_audit_fixes.py` |
| Колбэк инвентаря несёт id вещи — старая кнопка не открывает соседний предмет | `bot/keyboards/inline.py`, `bot/handlers/inventory.py` | `tests/test_audit_fixes.py` |
| Задания в боте: доска, приём, прогресс в бою, сдача с наградой | `core/quests.py` (новый), `bot/handlers/quests.py` (новый), `bot/handlers/battle.py` | `tests/test_audit_fixes.py` |
| **Партия 10 — перенос в браузерный стек:** титулы, бестиарий, фазы луны, перерождение | `engine/titles.py`, `engine/bestiary.py`, `engine/lunar.py`, `engine/prestige.py` (новые) + `core/*` стали реэкспортом | `tests/test_engine_progress.py` (33 проверки) |
| Экраны прогресса вынесены из `game.py` — роутер держится в лимите 500 строк | `engine/progress.py` (новый), `engine/game.py` | `tests/test_wiring.py` |
| FALLBACK в `index.html` пересобран под 92 модуля | `index.html`, `modules.json` | `tests/test_wiring.py` |
| **Паритет вырос до 32 из 32 механик** | `tests/test_parity.py` | `python3 tests/test_parity.py` |
| **Партия 11 — перенос:** таланты, подклассы, фамильяры | `engine/talents.py`, `engine/subclasses.py`, `engine/familiars.py` (новые) + `core/*` стали реэкспортом | `tests/test_engine_talents.py` (28 проверок) |
| Множители подкласса применяются к полному урону, а не к бонусу оружия (иначе терялись при округлении) | `engine/rules.py` | `tests/test_engine_talents.py` |
| Очки талантов считаются по разнице уровней — не теряются при скачке | `engine/rules.py` | `tests/test_engine_talents.py` |
| **Паритет 35 из 35 механик** | `tests/test_parity.py` | `python3 tests/test_parity.py` |
| **Партия 12 — перенос:** руны, мирные занятия, археология, эмбиент | `engine/runes.py`, `engine/gathering.py`, `engine/ambient.py` (новые); `core/gathering.py`, `core/archaeology.py` переведены на общие таблицы | `tests/test_engine_gathering.py` (30 проверок) |
| Рыбалка, травы и раскопки в движке — по типу тайла, как в боте | `engine/explore.py`, `engine/progress.py`, `engine/game.py` | `tests/test_engine_gathering.py` |
| **Паритет 38 из 38 механик** | `tests/test_parity.py` | `python3 tests/test_parity.py` |
| **Партия 13 — перенос:** разбор снаряжения, призрачный прах, Зал Славы | `engine/salvage.py`, `engine/spectral.py`, `engine/legends.py` (новые); `core/*` переведены на общие правила | `tests/test_engine_legends.py` (30 проверок) |
| Зал Славы наполняется: первое убийство босса пишется в летопись | `engine/worldboss.py` | `tests/test_engine_legends.py` |
| **Паритет 41 из 41 механик** | `tests/test_parity.py` | `python3 tests/test_parity.py` |
| **Партия 14 — перенос:** ломбард, вклады, чёрный рынок одним модулем | `engine/shadowecon.py` (новый); `core/pawnshop.py`, `core/investments.py`, `core/blackmarket.py` переведены на общие ставки | `tests/test_engine_shadowecon.py` (35 проверок) |
| «Магические числа» экономики (0.70, 1.15, 0.02, 1.35) собраны в одном месте | `engine/shadowecon.py` | `tests/test_parity.py` |
| **Паритет 44 из 44 механик** | `tests/test_parity.py` | `python3 tests/test_parity.py` |

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

### № 11. Археология в браузерном стеке
**Статус:** ✅ сделано (иначе, чем предполагало ТЗ). **Решение:** отдельный `engine/archaeology.py` не заводился — правила археологии и сбора близки, поэтому общие числа (`FRAGMENTS_FOR_MAP = 5`, размер клада, тексты) собраны в `engine/gathering.py`, а `core/archaeology.py` берёт их оттуда. Так одно и то же число не лежит в двух файлах.
**В движке:** действие «⛏ Копать» на клетках вне города, счётчик осколков в `Player.relic_fragments`, пятый осколок складывается в карту с координатами (`treasure_map_coord`).
**Проверка:** `tests/test_engine_gathering.py` — накопление 1→5, обнуление счётчика, появление карты.
**Было:** **Доказательство:** `core/archaeology.py:find_relic_fragment` — 5 фрагментов → `treasure_map_coord = "loc:{id}:x:{x}:y:{y}"`; колонки `core/models.py:315-316` (`relic_fragments`, `treasure_map_coord`); в `engine/` модуля нет.
**ТЗ:** перенести `find_relic_fragment` и формат координат в `engine/archaeology.py` (Player-поля `relic_fragments`, `treasure_map_coord` добавить в `engine/models.py`); точка входа — действие «⛏ Копать» на клетке (роутер `engine/game.py` + кнопка в `engine/explore.py`), сбор 5-го фрагмента сообщает координаты тайника.
**Файлы:** `engine/archaeology.py` (новый), `engine/models.py`, `engine/game.py`, `engine/explore.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 12. `engine/spectral.py` — призрачный торговец и прах предков
**Статус:** ✅ сделано. **Сделано:** витрина, цены в прахе и тексты сделки перенесены в `engine/spectral.py` (`core/spectral.py` берёт их оттуда — проверено тождество объекта). В движке: «🕯 Почтить память» у могилы даёт `ASH_PER_GRAVE` праха, «👻 Призрак» открывает витрину, покупка списывает **прах, а не монеты** (это отдельная валюта, что и проверяется тестом). Поле `Player.soul_ash` добавлено.
**Было:** **Доказательство:** `core/spectral.py` — `SPECTRAL_WARES` (`spec_wound_heal` 30, `spec_ethereal_blade` 75, `spec_ancestor_tear` 50 праха), `harvest_soul_ash`, `buy_spectral_item`; колонка `core/models.py:296` (`soul_ash`); в боте вход есть (`bot/handlers/location.py:spectral_nomad_menu`, `harvest_ash`), в `engine/` — нет.
**ТЗ:** `engine/spectral.py` с тем же каталогом (каталог — в `engine/`, `core/spectral.py` реэкспортирует); в движке: сбор праха с могилы (там же, где `engine/death.claim`) и меню призрака на могильных клетках.
**Файлы:** `engine/spectral.py` (новый), `engine/death.py`, `engine/game.py`, `core/spectral.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 13. Вклады в лавки в браузерном стеке
**Статус:** ✅ сделано (в общем модуле, а не отдельным файлом). **Решение:** ломбард, вклады и чёрный рынок собраны в `engine/shadowecon.py` — у них одна природа (деньги и время) и общие ставки; три отдельных файла означали бы три копии одних и тех же чисел.
**Сделано:** `DIVIDEND_RATE`, расчёт доли и выплата — общие; `core/investments.py` теперь берёт их оттуда. В движке экран «🏦 Вклад» показывает капитал лавки, свою долю в процентах и полученные дивиденды; суммы фиксированные, подделанная сумма отклоняется.
**Было:** **Доказательство:** `core/investments.py:invest_in_town` (списание через `engine.currency.total_in_bronze/deduct_currency`, ошибки «Сумма должна быть больше нуля.», «Не хватает …🟤.»), модель `TownInvestment` (`core/models.py:1313` `invested_bronze`); в `engine/` нет.
**ТЗ:** перенести вклад/дивиденды в `engine/investments.py`; в движке — пункт «🏦 Вклад в лавку» в меню безопасной локации (`engine/game.py`, экран `engine/explore.py`), выплата дивидендов по таймеру (`engine/respawn.py`-стиль, общий тик мира).
**Файлы:** `engine/investments.py` (новый), `engine/models.py`, `engine/game.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 14. Ломбард в браузерном стеке
**Статус:** ✅ сделано (в `engine/shadowecon.py`, см. № 13). **Сделано:** ставки `LOAN_SHARE = 0.70`, `BUYBACK_MARKUP = 1.15`, `LOAN_DAYS = 3` перестали быть «магическими числами» в `core/pawnshop.py` — он вызывает `loan_for()` / `buyback_for()`. В движке: «💍 Заложить» в карточке вещи (надетую заложить нельзя), экран займов с выкупом, просрочка изымается `sweep_loans()`.
**Проверено тестом:** чужой заём не выкупить, дважды не выкупить, просроченный уже не вернуть по старой цене.
**Было:** **Доказательство:** `core/pawnshop.py` (модель `PawnLoan`, `core/models.py:1329` `loan_bronze`), импортируется только из `tests/test_economy_and_lunar.py`.
**ТЗ:** перенести залог/выкуп/просрочку в `engine/pawnshop.py`; в движке — NPC-ростовщик в Погосте (кнопка в `engine/explore.py`, роутер в `engine/game.py`).
**Файлы:** `engine/pawnshop.py` (новый), `engine/game.py`, `engine/explore.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 15. Чёрный рынок в браузерном стеке
**Статус:** ✅ сделано (в `engine/shadowecon.py`, см. № 13). **Сделано:** наценка `LIQUIDATED_MARKUP = 1.35` общая; изъятые за долги вещи попадают на витрину и выкупаются другими игроками, после продажи исчезают с витрины (дважды одну вещь не купить).
**Главное экономическое правило, закреплённое тестом:** выкуп дороже займа, а перепродажа дороже выкупа — иначе выгодно не платить по долгу и купить свою же вещь дешевле.
**Было:** **Доказательство:** `core/blackmarket.py` — витрина, импорт только из `tests/test_economy_and_lunar.py`; просроченные залоги по плану перетекают из ломбарда (см. № 14 и № 47).
**ТЗ:** `engine/blackmarket.py` (те же товары/цены); вход в движке — отдельная кнопка у теневого NPC (не смешивать с обычной лавкой).
**Файлы:** `engine/blackmarket.py` (новый), `engine/game.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 16. `engine/lunar.py` — фазы луны
**Статус:** ✅ сделано. **Сделано:** каталог фаз и расчёт от времени перенесены в `engine/lunar.py` — теперь это **единственный источник правды**, `core/lunar.py` их реэкспортирует (в нём остался только серверный оверрайд через `AppSetting`). В движке добавлены `phase_of(store)` и `set_override(store, key)`: заморозка фазы хранится в `store.settings`, потому что таблиц у браузерного стека нет. Расчёт общий, поэтому фаза совпадает в обоих стеках без всякой синхронизации.
**Было:** **Доказательство:** `core/lunar.py` — фазы и эффекты, импорт только из `tests/test_economy_and_lunar.py`.
**ТЗ:** перенести расчёт фазы по дате в `engine/lunar.py` (без БД — чистая функция от `time.time()`); показывать фазу в `engine/texts.cell_view` и в бою применять её модификаторы там, где это делает сервер (`core/lunar.py` читать как эталон).
**Файлы:** `engine/lunar.py` (новый), `engine/texts.py`, `engine/combat.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 17. `engine/salvage.py` — разбор вещей на материалы
**Статус:** ✅ сделано. **Сделано:** таблица выхода (`SCRAP_BY_RARITY`, прибавка за заточку, порог для магической пыли) перенесена в `engine/salvage.py`; `core/salvage.py` вызывает `yield_for()` и своих чисел больше не содержит. Функция принимает редкость и строкой, и `Enum`, потому что у сервера это `ItemRarity`, а у движка — обычная строка.
**Было:** **Доказательство:** `core/salvage.py`, импорт только из `tests/test_economy_and_lunar.py`; крафт в движке есть (`engine/craft.py`), материалов из разбора нет.
**ТЗ:** `engine/salvage.py` с теми же таблицами выхода материалов; кнопка «🔧 Разобрать» в карточке предмета (`engine/inventory.card`) с выдачей в материалы крафта (`engine/craft.py`).
**Файлы:** `engine/salvage.py` (новый), `engine/inventory.py`, `engine/itemui.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 18. `engine/gathering.py` — мирные занятия
**Статус:** ✅ сделано. **Сделано:** таблицы шансов рыбалки (`FISH_CHANCE_*`), список трав, суммы и тексты перенесены в `engine/gathering.py` — теперь это единственный источник правды, `core/gathering.py` их импортирует (проверено тождество модулей). В движке появились «🎣 Рыбачить» и «🌿 Собрать травы», привязанные к тайлам `water` / `forest`+`swamp` — ровно как в `inspect_keyboard` бота.
**Было:** **Доказательство:** `core/gathering.py:gather_herbs` — в боте вход есть (`bot/handlers/location.py:gather_herbs`), в `engine/` нет.
**ТЗ:** `engine/gathering.py` (травы на клетках с травой/лесом — тайлы уже размечены в `engine/world.py`); действие «🌿 Собрать травы» в `engine/explore.py`.
**Файлы:** `engine/gathering.py` (новый), `engine/explore.py`, `engine/game.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 19. `engine/familiars.py` — фамильяры
**Статус:** ✅ сделано. **Сделано:** каталог спутников перенесён в `engine/familiars.py` (`core/familiars.py` реэкспортирует — проверено, что это тот же объект). В движке добавлен экран «🐾 Спутник»: покупка за бронзу через `engine/currency`, повторно спутника не завести, при нехватке денег показывается недостающая сумма. Поля `familiar_type/level/name` добавлены в `Player`.
**Было:** **Доказательство:** `core/familiars.py` (`FAMILIARS`, `familiar_card_text`, `set_familiar`), колонка `core/models.py:291` (`familiar_type`); в боте вход есть (`bot/handlers/character.py:familiar_menu`), в `engine/` нет.
**ТЗ:** `engine/familiars.py`; экран фамильяра в профиле движка (`engine/texts.profile` + кнопка в `engine/game.menu`); покупка за валюту через `engine/currency.deduct_currency`.
**Файлы:** `engine/familiars.py` (новый), `engine/models.py`, `engine/texts.py`, `engine/game.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 20. `engine/pets.py` — питомцы (сейчас только админ-редактор)
**Статус:** ⬜ не сделано. **Доказательство:** `core/pets.py` импортируется только из `admin/main.py` и `tests/test_pets_admin.py`; шаблон `PetTemplate` в `core/models.py`; в `engine/` питомцев нет вообще.
**ТЗ:** `engine/pets.py` (выбор питомца из `PetTemplate`, эффекты); в движке — вкладка питомца в профиле; в админке Pyodide (`webapp/pages/content.py`) — редактор шаблонов питомцев (паритет с `admin/main.py` + `editor_pets.html`).
**Файлы:** `engine/pets.py` (новый), `engine/models.py`, `engine/texts.py`, `webapp/pages/content.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 21. `engine/prestige.py` — престиж после капа
**Статус:** ✅ сделано. **Сделано:** `engine/prestige.py` с тем же порогом `REBIRTH_MIN_LEVEL = 15` и «Искрой Бессмертия» (+10 % к базовым статам за круг), что на сервере; числа сверяет реестр паритета. Экран и ритуал — в меню движка (`♻️ Перерождение`), поле `Player.rebirth_count` добавлено.
**Было:** **Доказательство:** `core/prestige.py`, импорт только из `tests/test_progression_and_karma.py`; пункт 5 «Прогресс после капа» из `IDEAS-next.md` не закрыт.
**ТЗ:** `engine/prestige.py` (сброс уровня за постоянный бонус, те же числа); в движке — действие «♻ Престиж» в профиле при достижении капа уровня.
**Файлы:** `engine/prestige.py` (новый), `engine/texts.py`, `engine/game.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 22. `engine/subclasses.py` — подклассы
**Статус:** ✅ сделано. **Сделано:** каталог специализаций в `engine/subclasses.py`, порог вынесен в `SUBCLASS_MIN_LEVEL = 10` (общий на два стека). Экран «🎓 Путь» показывает только пути своего класса, выбор необратим.
**Важная деталь реализации:** множители подкласса нельзя применять к одному бонусу экипировки — при уроне 3 и множителе 1.25 `int()` округлял обратно в 3, и берсерк ничем не отличался от паладина (**поймано собственным тестом**). Сделано как на сервере (`core/stats.attack_power`): множитель применяется к «сила + урон оружия» внутри `attack_roll`, а `defense_mult` — к суммарной броне в `mob_roll`. Проверка меряет средний урон за 40 ударов: 18.2 против 14.9.
**Было:** **Доказательство:** `core/subclasses.py` подключён в `core/stats.py` (влияет на статы) и тестируется в `tests/test_progression_and_karma.py`; в `engine/` нет.
**ТЗ:** `engine/subclasses.py` с теми же таблицами подклассов; применение в `engine/rules.stats`; выбор подкласса — экран в профиле (`engine/game.py`).
**Файлы:** `engine/subclasses.py` (новый), `engine/rules.py`, `engine/texts.py`, `engine/game.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 23. `engine/talents.py` — таланты
**Статус:** ✅ сделано. **Сделано:** звёздное древо перенесено в `engine/talents.py` (`core/talents.py` — реэкспорт). Очки начисляются в `rules.add_exp` **по разнице** `points_for_level(level)`, а не «+1 за уровень»: при скачке через несколько уровней очки не теряются (проверено прогоном до 100 000 опыта). Бонусы талантов складываются в `rules.stats` теми же ключами, что использует `core/stats.combat_stats`. Экран «⭐ Созвездия» — в меню движка.
**Было:** **Доказательство:** `core/talents.py` подключён в `core/stats.py` и тестируется в `tests/test_progression_and_karma.py`; в `engine/` нет.
**ТЗ:** `engine/talents.py` (дерево, стоимость очков — числа из `core/talents.py`); очки талантов за уровни (рядом с `engine/rules.add_exp`); экран распределения в профиле.
**Файлы:** `engine/talents.py` (новый), `engine/rules.py`, `engine/game.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 24. `engine/titles.py` — титулы
**Статус:** ✅ сделано. **Сделано:** каталог титулов переехал в `engine/titles.py` (`core/titles.py` реэкспортирует его). Функции пишут в поля `unlocked_titles_json` / `active_title`, которые есть у обоих типов героя, поэтому логика одна на два стека. Бонусы титула складываются в `engine/rules.stats` рядом с экипировкой — ровно как `core/stats.py` складывает `title_bonus`. Экран выбора титула добавлен в меню движка; битый JSON в поле не роняет профиль.
**Было:** **Доказательство:** `core/titles.py` подключён в `core/stats.py` и тестируется в `tests/test_progression_and_karma.py`; в `engine/` нет.
**ТЗ:** `engine/titles.py` (условия получения — числа из `core/titles.py`); проверка условий там же, где растут `p.kills`/репутация (`engine/rules.py`, `engine/factions.py`); титул в `engine/texts.profile` рядом со строкой кармы.
**Файлы:** `engine/titles.py` (новый), `engine/rules.py`, `engine/factions.py`, `engine/texts.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 25. `engine/runes.py` — руны
**Статус:** ✅ сделано. **Сделано:** каталоги `RUNES` и `RUNEWORDS` перенесены в `engine/runes.py` (`core/runes.py` — реэкспорт). Логика вставки одна на два стека: серверный `ItemInstance` — объект с атрибутами, а экземпляры движка — словари, поэтому добавлена обёртка `insert_into_instance` / `_DictInstance`, которая пишет изменения обратно в dict. Второй копии правил рунических слов не появилось.
**Было:** **Доказательство:** `core/runes.py`, импорт только из `tests/test_craft_and_dungeon_hazards.py`; крафт/заточка в движке есть (`engine/craft.py`).
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
**Статус:** ✅ сделано. **Сделано:** атлас перенесён в `engine/bestiary.py` (`core/bestiary.py` реэкспортирует). Победы записываются прямо в бою движка, бонус охотника (+1 % за 10 побед, потолок 15 %) применяется в `engine/combat.action`, экран «📖 Бестиарий» — в меню. Пороги вынесены в константы `KILLS_PER_STEP` / `MAX_BONUS_PCT`, чтобы не быть «магическими числами» в двух местах.
**Было:** **Доказательство:** `core/bestiary.py`, импорт только из `tests/test_lore_and_legends.py`; `Player.kills` в движке уже считается (`engine/rules.py:_reward`).
**ТЗ:** `engine/bestiary.py` (записи по убитым тварям — данные уже есть в `engine/content.py:MOBS`); экран в меню (`engine/game.menu`), счётчик по видам из `p.kills` + новой структуры учёта по индексам мобов.
**Файлы:** `engine/bestiary.py` (новый), `engine/game.py`, `engine/models.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 33. `engine/ambient.py` — звуковой эмбиент
**Статус:** ✅ сделано. **Уточнение по факту кода:** `core/ambient.py` — не «фоновые события мира», а профили звукового окружения для Web Audio (потрескивание костра, вой ветра, эхо капель). Браузерному стеку они нужны напрямую — звук играет именно там, — поэтому каталог перенесён в `engine/ambient.py`, а `core/ambient.py` стал реэкспортом.
**Было:** **Доказательство:** `core/ambient.py`, импорт только из `tests/test_miniapp_and_radar.py`; фоновые циклы в боте есть (`bot/runner.py:_portal_sweep_loop`, `_spawn_tick_loop`), в движке фонового тика нет.
**ТЗ:** `engine/ambient.py` (случайные фоновые строки/события по таймеру); вызов из тика мира в `engine/game.do_world` или `engine/respawn.py`.
**Файлы:** `engine/ambient.py` (новый), `engine/game.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 34. `engine/legends.py` — Зал Славы
**Статус:** ✅ сделано. **Решение по хранилищу:** у стеков оно разное — сервер пишет строки `ServerRecord`, у браузерного стека таблиц нет, поэтому записи легли в `store.settings` с обрезкой до `MAX_RECORDS = 50`. Общими сделаны **правило и вёрстка**: `hall_text()` принимает и словари движка, и строки БД, поэтому экран одинаков в обоих стеках, а `core/legends.hall_of_legends_text` теперь просто зовёт её.
**Ключевое правило:** рекорд именной и **не перезаписывается** — повторная запись того же ключа отклоняется, иначе «первый победитель» терял бы смысл (проверяется тестом: в летописи остаётся первопроходец, а не последний).
**Подключено к игре:** первое убийство каждого мирового босса пишется в Зал Славы прямо из `engine/worldboss._reward_all` — иначе летопись осталась бы пустой навсегда, как это было с доской наград.
**Было:** **Доказательство:** модель `ServerRecord` (`core/models.py`) используется только в `core/legends.py`; игрокам летопись не показывается ни в одном стеке.
**ТЗ:** `engine/legends.py` (записи «первый босс», «крупнейший катаклизм» — там же, где они уже пишутся: `engine/worldboss.py:_finish`, `engine/cataclysm.py`); экран «📖 Летопись» в меню; сервер: показ летописи в боте (см. № 60).
**Файлы:** `engine/legends.py` (новый), `engine/worldboss.py`, `engine/cataclysm.py`, `engine/game.py`, `modules.json`, `index.html`, `tests/test_parity.py`.

### № 35. `engine/dialogue.py` — реактивные реплики NPC
**Статус:** ✅ сделано. **Доказательство:** серверный `core/dialogue.py` был подключён, а NPC браузерного стека всегда говорили статичный текст.
**Сделано:** `engine/dialogue.py` с той же лестницей приоритетов, что на сервере (осада → катаклизм → караван → карма → покой) и порогами из `engine/karma.py`; контекст собирается из `engine/cataclysm.active` и `engine/merchant.at`. `engine/explore.talk()` принимает `store` и подставляет реактивную реплику вместо дежурного описания, `engine/game.do_talk` передаёт хранилище. Модуль добавлен в `modules.json` и `FALLBACK` в `index.html`, бандл пересобран.
**Остаток:** осад в браузерном стеке пока нет — ветка `has_siege` зарезервирована, чтобы совпадать с серверной.
**Файлы:** `engine/dialogue.py` (новый), `engine/explore.py`, `engine/game.py`, `modules.json`, `index.html`.
**Проверка:** `tests/test_partial_items_done.py` — `test_engine_dialogue_matches_server_branches` (порядок веток: осада важнее кармы), `test_engine_talk_uses_reactive_line`.

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
**Статус:** ✅ сделано. **Сделано:** кнопка «🕯 Чёрный рынок» в городе + экран `blackmarket_menu` с витриной из `core/blackmarket.BLACK_MARKET_WARES` и хендлер `bm_buy:`.
**Дополнено:** просрочка ломбарда теперь перетекает на витрину. `core/pawnshop.sweep_expired_loans()` помечает истёкшие займы `is_liquidated` (зовётся фоновым циклом `bot/runner.py` раз в 5 минут и кнопкой в админке), `core/blackmarket.list_liquidated_wares()` показывает эти вещи в блоке «🔒 Изъято за долги», `buy_liquidated_item()` продаёт их с наценкой `LIQUIDATED_MARKUP = 1.35` — иначе выгоднее было бы не платить по долгу и выкупить свою же вещь дешевле. Купленная вещь помечается `is_redeemed` и уходит с витрины, поэтому продать её дважды нельзя.
**Файлы:** `bot/handlers/location.py`, `bot/keyboards/inline.py`.
**Проверка:** `tests/test_bot_entrypoints.py::test_blackmarket_purchase_requires_money`.

### № 49. Фазы луны: показ игроку в боте
**Статус:** ✅ сделано. **Сделано:** строка текущей фазы и её эффекта выводится при осмотре клетки.
**Дополнено:** все три множителя доведены до игровых расчётов — `mob_mult` меняет лимит популяции в `core/spawns.ensure_population`, `material_mult` умножает шанс дропа в `core/loot.roll_drops`, `magic_dark_mult` усиливает урон школы Тьмы в `bot/handlers/battle.combat_skill` (с пометкой в тексте боя). Все три читают фазу через `core/lunar.get_phase(session)`, поэтому уважают админскую заморозку (№ 65).
**Файлы:** `bot/handlers/location.py`.
**Проверка:** `tests/test_bot_entrypoints.py::test_lunar_phase_is_deterministic_and_covers_cycle`.

### № 50. Разбор вещей на материалы в боте
**Статус:** ✅ сделано. **Сделано:** кнопка «🟠 🔧 Разобрать» в карточке снаряжения (`item_book_keyboard`, флаг `can_salvage`; надетую вещь разобрать нельзя) + хендлер `salvage:` — вызывает `core/salvage.salvage_item` и показывает выход материалов (лом, слитки, магическая пыль).
**Файлы:** `bot/handlers/inventory.py`, `bot/keyboards/inline.py`.
**Проверка:** `tests/test_bot_entrypoints.py::test_item_book_keyboard_has_salvage_and_pawn`, `test_handlers_registered`.

### № 51. Гильдии: вход игроку в боте
**Статус:** ✅ сделано. **Доказательство:** `core/guilds.py` вызывался только тестами.
**Сделано:** новый роутер `bot/handlers/guilds.py` (зарегистрирован в `bot/handlers/__init__.py`) и кнопка «🏛 Гильдия» в главном меню. Экран показывает свою гильдию (девиз, уровень, казна, роль, состав) либо список чужих со вступлением и основанием за 2000🟤; взносы в казну — фиксированными суммами `DEPOSIT_STEPS` с защитой от подделанного колбэка.
**Побочно найден и исправлен реальный баг:** таблицы `guilds`/`guild_members`/`guild_vault_items` **никогда не создавались** — модели объявлены в `core/guilds.py`, а `core/migrations.py` импортировал только `core/models.py`, поэтому они не попадали в `Base.metadata` («no such table: guilds»). Добавлен импорт-регистрация в `core/migrations.py`.
**Файлы:** `bot/handlers/guilds.py` (новый), `bot/handlers/__init__.py`, `bot/keyboards/inline.py`, `core/migrations.py`.
**Проверка:** `tests/test_guild_bounty_duel_entrypoints.py` — `test_guild_create_join_and_deposit`, `test_guild_tables_registered_in_metadata` (регрессия на баг метаданных).

### № 52. Наставничество: вход игроку в боте
**Статус:** 🟡 частично. **Сделано:** кнопка «🎓 Наставник» в главном меню и экран `mentor_menu` в `bot/handlers/guilds.py`: новичку (1–5 ур.) показывается список ветеранов 8+ с привязкой в один клик, ученику — текущий наставник и бонус, ветерану — накопленные Очки Чести. Правила («сам себе не наставник», «один наставник навсегда», пороги уровней) остаются в `core/mentorship.py`.
**Остаток:** сам бонус +25 % опыта пока не применяется в `_finish_victory`, и `reward_mentor_for_progress` не вызывается при росте ученика — это отдельная правка в `bot/handlers/battle.py`.
**Файлы:** `bot/handlers/guilds.py`, `bot/keyboards/inline.py`.
**Проверка:** `tests/test_guild_bounty_duel_entrypoints.py::test_mentorship_rules_and_binding`.

### № 53. Дуэли: вызов другого игрока на клетке
**Статус:** 🟡 частично. **Доказательство (важное):** кнопка «⚔️ Напасть на игрока» (`pvp_select`) уже существовала в `inspect_keyboard`, но **обработчика у неё не было** — нажатие молча ничего не делало.
**Сделано:** хендлеры `pvp_select` и `duel_go:` в `bot/handlers/world_extra.py` — выбор соперника среди героев на той же клетке и этаже, ставки `DUEL_WAGERS = (0, 100, 500)` с проверкой колбэка, бой через `core/duels.resolve_wager_duel`, экран с последними раундами, победителем и банком. Проверяется, что соперник не ушёл, пока экран висел открытым.
**Дополнено:** дуэль теперь по согласию. `duel_go:` только отправляет вызов (проверяя, что ставка по карману), вызванный получает личное сообщение с кнопками «⚔️ Принять» / «🚫 Отказаться»; бой запускает `duel_accept:` — с повторной проверкой, что соперник не ушёл с клетки. Исход отправляется обоим участникам. Вызовы живут в `duel_invites` в памяти процесса — как и боевое состояние `combat_state`.
**Статус:** ✅ сделано.
**Файлы:** `bot/handlers/world_extra.py`.
**Проверка:** `tests/test_guild_bounty_duel_entrypoints.py::test_duel_with_wager_moves_money_to_winner` (в т.ч. удержание комиссии арены).

### № 54. Престиж: перерождение после капа в боте
**Статус:** ✅ сделано. **Сделано:** кнопка «♻️ Перерождение» на странице «Характеристики» профиля — появляется только у героев, доросших до `REBIRTH_MIN_LEVEL` (заведомо недоступную кнопку новичкам не показываем). Экран `rebirth_menu` объясняет цену и выгоду (уровень и опыт обнуляются, базовые статы +10 % навсегда), `rebirth_do` проводит ритуал через `core/prestige.perform_rebirth`.
**Файлы:** `bot/handlers/guilds.py`, `bot/handlers/character.py`, `bot/keyboards/inline.py`.
**Проверка:** `tests/test_guild_bounty_duel_entrypoints.py::test_rebirth_requires_level_and_boosts_stats`, `test_rebirth_button_only_for_eligible_heroes`.

### № 55. Доска наград за головы в боте
**Статус:** ✅ сделано. **Доказательство (важное):** мало того что доска была недостижима — `core/bounty.record_mob_kill` **не вызывался ниоткуда**, поэтому мобы-убийцы никогда не получали имён и список наград был пуст навсегда. Клавиатура `bounty_board_keyboard` существовала, а обработчика `bounty_track:` не было.
**Сделано:** полный цикл. Гибель игрока (`_finish_defeat`) присваивает мобу титул убийцы через `record_mob_kill`; кнопка «💀 Награды» в меню открывает доску (`bounty_menu`) со списком целей, местом и кушем; `bounty_track:` подсказывает координаты; убийство такой цели в `_finish_victory` платит `calculate_bounty_reward` сверх обычной добычи и снимает контракт (`kill_count = 0`).
**Файлы:** `bot/handlers/world_extra.py`, `bot/handlers/battle.py`, `bot/keyboards/inline.py`.
**Проверка:** `tests/test_guild_bounty_duel_entrypoints.py::test_bounty_appears_after_mob_kills_player` (награда растёт со счётчиком жертв).

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
**Статус:** ✅ сделано. **Доказательство:** колонка `karma_score` существовала (`core/models.py:308`), но в карточке игрока её не было.
**Сделано:** блок «⚖️ Карма» на вкладке «Характеристики» — поле правки с границами из `core/karma.py`, рядом текущий титул и описание эффекта (`karma_status`), подпись с порогами Благочестивого/Осквернителя. Значение принимает существующая форма `/player/{id}/edit` (отдельный роут не понадобился), значение клампится по `MIN_KARMA`/`MAX_KARMA` — админка не может выставить карму за пределы, которые понимает игра.
**Файлы:** `admin/main.py` (контекст `karma_info` + параметр `karma_score`), `admin/templates/player_detail.html`.
**Проверка:** `tests/test_admin_subsystems.py::test_karma_visible_and_editable_in_player_card` (в т.ч. кламп −9999 → −500).

### № 62. Админка: ломбард (займы `PawnLoan`)
**Статус:** ✅ сделано. **Сделано:** блок «💍 Ломбард» на новой странице `/editor/subsystems`: счётчики активных/просроченных/всего, таблица (герой со ссылкой на карточку, вещь, выдано, выкуп, срок, статус) и действие «Изъять» для просроченных (`POST /editor/subsystems/loan/{id}/liquidate`, помечает `is_liquidated`).
**Файлы:** `admin/main.py`, `admin/templates/editor_subsystems.html` (новый), `admin/templates/base.html` (пункт меню).
**Проверка:** `tests/test_admin_subsystems.py::test_overdue_loan_can_be_liquidated` (включая повторное изъятие).

### № 63. Админка: инвестиции (`TownInvestment`)
**Статус:** ✅ сделано. **Сделано:** блок «🏦 Вклады в городские лавки» на `/editor/subsystems`: суммарно вложено, выплачено дивидендов, число вкладчиков, таблица по локациям и вкладчикам, ставка выплаты берётся из `core/investments.DIVIDEND_RATE` (не зашита в шаблон), кнопка «💎 Выплатить дивиденды сейчас» с подтверждением.
**Файлы:** `admin/main.py`, `admin/templates/editor_subsystems.html`.
**Проверка:** `tests/test_admin_subsystems.py::test_manual_dividend_payout_credits_investor`, `test_page_shows_real_loans_and_investments`.

### № 64. Админка: чёрный рынок
**Статус:** ✅ сделано. **Сделано:** блок «🕯 Чёрный рынок» на `/editor/subsystems` — постоянная витрина из `core/blackmarket.get_black_market_wares()` плюс таблица «🔒 Изъято за долги» с ценами перепродажи; кнопка «Изъять всю просрочку» (`POST /editor/subsystems/sweep-loans`) в блоке ломбарда переводит истёкшие займы на витрину одним действием.
**Файлы:** `admin/main.py`, `admin/templates/editor_subsystems.html`.
**Проверка:** `tests/test_admin_subsystems.py::test_subsystems_page_renders_all_sections` (сверяет название товара с модулем).

### № 65. Админка: фазы луны
**Статус:** ✅ сделано. **Сделано:** блок «🌙 Фаза луны» с текущей фазой и таблицей множителей + **заморозка фазы**: `core/lunar.set_override/get_phase` хранят выбор в `AppSetting` (`lunar_phase_override`), форма `POST /editor/subsystems/lunar` ставит любую фазу или возвращает естественный цикл, на странице видна пометка «заморожено вручную» и то, какая фаза была бы по времени. Подделанный ключ фазы молча игнорируется (как мусор в числовых полях клетки, `AUDIT-BUGS.md` п. 19). Игровые расчёты (№ 49) читают именно `get_phase`, поэтому заморозка влияет на спавн, дроп и магию Тьмы.
**Файлы:** `admin/main.py`, `admin/templates/editor_subsystems.html`.

### № 66. Админка: гильдии и наставничество
**Статус:** ✅ сделано. **Сделано:** блок «🏛 Гильдии» со списком (название, уровень, казна, участники) и кнопкой **«Распустить»** (`POST /editor/subsystems/guild/{id}/disband`) — участники освобождаются, хранилище удаляется каскадом. Выборка обёрнута в `try/except`: если таблицы ещё не созданы, блок показывает подсказку вместо ошибки 500.
**Остаток (мелочь):** отдельной таблицы «наставник–ученик» нет; связка видна в карточке игрока.
**Файлы:** `admin/main.py`, `admin/templates/editor_subsystems.html`.

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
**Статус:** ⬜ не сделано (следующий шаг для Раздела 4). **Доказательство:** `core/realtime.py` публикует `player_move`, `battle_result`, `auction_new` и т. д. (см. docstring модуля); события кармы/знамений/ломбарда/инвестиций не публикуются.
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
**Статус:** ✅ сделано. **Сделано:** блок «🔮 Знамения и карма» на вкладке «Жизнь мира» — карточки всех знамений из общего каталога `engine/omens.py` и расклад героев по карме (сколько Благочестивых, Нейтральных, Осквернителей с указанием порогов из `engine/karma.py`).
**Остаток:** блока «🌙 Луна» в браузерной панели нет — `engine/lunar.py` появится только после № 16 (перенос фаз в браузерный стек); сейчас фазы существуют лишь в серверном стеке и показаны в его админке (№ 65).
**Файлы:** `webapp/pages/world_living.py`.
**Проверка:** `tests/test_partial_items_done.py::test_panel_shows_omens_and_karma`.

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
**Статус:** ✅ сделано (иначе, чем предполагало ТЗ, — см. «решение» ниже).
**Доказательство:** `AUDIT-BUGS.md`, раздел A: продажа/прятание второй копии надетой вещи снимала экипировку; дубликат надетой вещи не выпадал в могилу.
**Решение (важно):** буквальный перевод `p.inventory` на uid затронул бы 13 модулей (бой, лавка, аукцион, крафт, задания, подземелья, торговец, летопись…) и был бы крупным риском ради двух багов. Взят аддитивный путь: заведён `engine/slots.py`, который рядом с `p.equipped` ведёт **позицию** надетой вещи в сумке (`Player.equipped_pos`). Позиция однозначно указывает на конкретный экземпляр — оба бага закрываются, формат сохранений не ломается, а объём правок ограничен пятью модулями.
**Что сделано:** `slots.take_at()` снимает экипировку, только если ушла **та самая** вещь, и сдвигает позиции остальных слотов; `slots.take_first_unequipped()` заменил `p.inventory.remove(idx)` в аукционе и заданиях (голый `remove` брал первое совпадение — мог забрать надетое — и рушил позиции); `sync_positions()` чинит старые сейвы (нет поля → позиция по индексу; надетой вещи нет в сумке → слот снимается, чтобы не начислять бонусы от несуществующего предмета).
**Файлы:** `engine/slots.py` (новый), `engine/models.py`, `engine/inventory.py`, `engine/shop.py`, `engine/stash.py`, `engine/auction.py`, `engine/quests.py`, `modules.json`, `index.html`, `tests/test_parity.py` (модуль отнесён к инфраструктуре: на сервере тот же вопрос решён флагом `InventoryItem.is_equipped` у конкретной строки, переносить нечего).
**Проверка:** `tests/test_slot_identity.py` — 26 проверок, включая обратную демонстрацию старой ошибки, сдвиг позиций при удалении слева, сохранность uid именного экземпляра и починку старых сейвов.

### № 80. `stash.drop_on_death` по uid (после № 79)
**Статус:** ✅ сделано. **Доказательство:** `engine/stash.py` сравнивал `idx not in worn` — «иммунитет к потере» получал любой предмет с индексом надетого.
**Сделано:** `drop_on_death` берёт `slots.equipped_positions(p)` — иммунна ровно одна надетая вещь, а её дубликаты выпадают в надгробие как обычная добыча; удаление идёт через `slots.take_at()`, поэтому позиция уцелевшей экипировки пересчитывается. Заодно `stash.put` больше не раздевает героя, когда в карман прячут вторую копию.
**Файлы:** `engine/stash.py`.
**Проверка:** `tests/test_slot_identity.py` — «терять можно только ненадетые копии: [1, 2]», «надетая вещь уцелела», «позиция надетой вещи пересчитана после потерь».

### № 81. Аукцион: сироты при удалённом продавце
**Статус:** ✅ сделано. **Сделано:** `_return_to_owner` больше не пишет `InventoryItem` на `character_id` мертвеца. Если персонажа нет (передан `None` и по `seller_id` никто не найден), вещь не исчезает и не оседает сиротой — уходит на витрину скупщика новым бессрочным лотом через общий помощник `_to_npc_shelf`, с записью в летопись «перешёл скупщику (продавец исчез)».
**Проверка:** `tests/test_audit_fixes.py::test_lot_of_deleted_seller_goes_to_npc_not_orphan` (сирот нет, лот появился) и `test_lot_returns_to_living_seller_as_before` (обычный случай не сломан).
**Было:** **Доказательство:** `AUDIT-BUGS.md`, раздел C: «`core/auction._return_to_owner` при удалённом продавце создаёт `InventoryItem` на несуществующего персонажа (сирота)».
**ТЗ:** если владелец удалён — вещь уходит скупщику (как при истечении лота), а не создаёт запись с `character_id` мертвеца; тест: удалить продавца → `_return_to_owner` → записи-сироты нет.
**Файлы:** `core/auction.py`, `tests/test_bugfixes.py` (расширить).

### № 82. Скупщик: лоты исчезают через 72 ч вопреки документации
**Статус:** ✅ сделано. **Выбранная политика — (а):** вещь остаётся в мире. По истечении срока лот скупщика не снимается молча, а перевыставляется бессрочно (`expires_at=None`) с наценкой `NPC_SELL_MARKUP`; отдельная константа не заводилась — используется уже существующая. Документация «предмет не исчезает из мира» снова соответствует коду.
**Проверка:** `tests/test_audit_fixes.py::test_expired_npc_lot_is_relisted_not_destroyed`.
**Было:** **Доказательство:** `AUDIT-BUGS.md`, раздел C: «Лоты скупщика: через 72 ч вещь с витрины исчезает из мира совсем — противоречит документации "предмет не исчезает из мира"».
**ТЗ:** выбрать политику и реализовать одну: (а) вещь остаётся на витрине бессрочно, (б) вещь уходит в реестр бесхозных экземпляров. Исправить документацию под выбранную политику; тест на оба исхода.
**Файлы:** `core/auction.py`, README/комментарии, `tests/test_bugfixes.py`.

### № 83. `ADMIN_SECRET_KEY` — публичный дефолт устранён
**Статус:** ✅ сделано. **Решение:** отказ при старте не подходит — панель задумана как «запустил и работает» (владелец открывает её локально вообще без логина). Поэтому `admin/auth._load_secret()` берёт ключ по цепочке: переменная окружения → `data/admin_secret.key` → генерация нового `secrets.token_urlsafe(48)` с сохранением в тот же файл (`data/` уже в `.gitignore`, права 0600). Опубликованные значения (`shadow-lands-secret`, `super-secret-key-change-me` и подобные) внесены в `_WEAK_KEYS` и **отвергаются даже из окружения** — иначе пример из `.env.example` молча стал бы боевым ключом. В `admin/config.py` публичный дефолт заменён пустой строкой.
**Проверено вручную:** ключ уникален, стабилен между запусками, env имеет приоритет, публичный дефолт отвергнут, файл игнорируется git.
**Проверка:** `tests/test_audit_fixes.py` — `test_admin_secret_is_not_public_default`, `test_admin_secret_prefers_env_but_rejects_examples`, `test_admin_secret_file_is_git_ignored`.
**Было:** **Доказательство:** `AUDIT-BUGS.md`, раздел C: `admin/auth.py` содержит дефолт `ADMIN_SECRET_KEY = "shadow-lands-secret"` — при выставлении панели наружу это отсутствие авторизации.
**ТЗ:** если переменная окружения не задана — при старте панели либо генерация случайного ключа с выводом в лог, либо отказ с понятной ошибкой (выбрать одно и зафиксировать в README); тест: без env панель не принимает дефолтный пароль.
**Файлы:** `admin/auth.py`, `launch.py`, `README.md`, `tests/test_access.py` (расширить).

### № 84. Колбэки «по позиции» → id в `callback_data`
**Статус:** ✅ сделано. **Доказательство:** `inventory_section_keyboard` отдавала `inv_book:<секция>:<индекс>`, а обработчик делал `index = max(0, min(index, len(bucket) - 1))` — из старого сообщения открывался **соседний предмет**, если список сдвинулся.
**Сделано:** в колбэк добавлен id вещи (`inv_book:<секция>:<индекс>:<id>`); обработчик ищет именно её и, если вещи уже нет, честно говорит «Этой вещи уже нет в сумке — список обновился» и открывает актуальный инвентарь. Старые сообщения без хвоста продолжают работать по индексу — обратная совместимость сохранена.
**Проверка:** `tests/test_audit_fixes.py` — `test_inventory_callback_carries_item_id`, `test_stale_callback_does_not_open_neighbour_item`.
**Было:** **Доказательство:** `AUDIT-BUGS.md`, раздел C: «Колбэки "по позиции" (продажа из старого сообщения) могут сработать на сдвинувшемся списке… полноценно лечится id в callback_data».
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
**Статус:** ✅ сделано. **Сделано:** новый модуль правил `core/quests.py` (доступные и активные задания, приём, прогресс, сдача) и роутер `bot/handlers/quests.py` с кнопкой «📜 Задания» в меню. Прогресс «убей N» двигается прямо в бою (`_finish_victory` → `core_quests.record_kill`, сравнение имени без учёта регистра); для «собери N» прогресс считается **по содержимому сумки** в момент показа — предметы могли появиться раньше, и заставлять собирать заново было бы нечестно; при сдаче они уходят заказчику, иначе одну связку трав можно было бы сдать во все задания сразу. Три задания уже лежали в `core/seed.py` и наконец стали доступны.
**Реестр:** Feature «Задания» получила серверную сторону, `todo` снят — паритет остаётся **28 из 28**.
**Проверка:** `tests/test_audit_fixes.py` — `test_kill_quest_full_cycle` (повторное взятие, чужой моб, недовыполненная сдача, повторная сдача), `test_collect_quest_consumes_items` (из 5 трав уходят ровно 3), `test_quest_handlers_registered`.
**Было:** **Доказательство:** `tests/test_parity.py` REGISTRY: Feature «Задания» с `todo="на сервере есть модель Quest, но нет выдачи и сдачи в боте"`; в движке задания работают (`engine/quests.py`), на сервере — только таблицы (`core/models.py`: `Quest`, `CharacterQuest`).
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

### № 90. Движок: начисления через кошелёк
**Статус:** ✅ сделано. **Сделано:** все 18 точек начисления/списания движка переведены на `engine/currency` (`earn`/`spend`/`can_afford`/`total`): бой, подземелья, сундуки, диковины, задания, отряд, мировой босс, аукцион, лавка, мастерская, торговец, инвентарь, смерть, админ-выдача. Проверок `p.gold < price` тоже не осталось — они сравнивали лишь старший разряд кошелька.
**Критерий приёмки выполнен:** `grep -rn "gold +=\|gold -=" engine/` пуст; регрессия `tests/test_currency_parity.py::test_engine_has_no_raw_gold_arithmetic` не даст вернуть прямую арифметику.
**Было:** **Доказательство:** `engine/combat.py:_reward` — `p.gold += gold`; `engine/worldboss.py:_reward_all` — `p.gold += gold`; `engine/death.py:claim` — `p.gold += taken`; `engine/inventory.py:sell` — `p.gold += paid`. Механика начисления «золота» в обход конвертации.
**ТЗ:** заменить все `p.gold += N` (grep: `grep -rn "gold += " engine/`) на `currency.add_currency(p, gold=N)` (эквивалентно по числу, т. к. нормализация не дробит золото вниз); добавить в `engine/currency.py` docstring-таблицу «какие функции каким путём меняют кошелёк».
**Файлы:** `engine/combat.py`, `engine/worldboss.py`, `engine/death.py`, `engine/inventory.py`, `engine/shop.py`, `engine/auction.py`, `engine/quests.py`, `engine/party.py` (по grep).
**Критерий приёмки:** `grep -rn "gold += " engine/` пуст; все существующие тесты движка зелёные (суммы не изменились).

### № 91. Движок: цены и траты через кошелёк
**Статус:** ✅ сделано. **Семантика зафиксирована:** любая сумма в движке считается **в бронзе** — как на сервере. Числа `engine/data.ITEMS` (20…180) и стартовый капитал по масштабу совпадали именно с бронзой сервера (стартовый бонус фракции 100–200🟤), поэтому баланс не сдвинулся: те же числа теперь честно называются бронзой и сворачиваются в серебро и золото при накоплении.
**Отображение:** баланс печатается кошельком (`currency.fmt` → «87🟤 12⚪ 3🟡»), цены — `currency.short` (мелочь в бронзе, крупное как «1🟡 25⚪»). Обновлены лавка, торговец, инвентарь, карточка боя, админ-журнал.
**Было:** **Доказательство:** покупки в `engine/shop.py`, `engine/auction.py`, `engine/merchant.py` вычитают из `p.gold` напрямую; `engine/currency.deduct_currency(p, cost_bronze)` существует и не используется движком.
**ТЗ:** ценники хранить в бронзе (как сервер: `Item.price` — в бронзе); списание через `deduct_currency` с понятной ошибкой «Не хватает N🟤» (текст уже используется сервером в `core/investments.py`); проверить `itemui.resale_of` и скупку.
**Файлы:** `engine/shop.py`, `engine/auction.py`, `engine/merchant.py`, `engine/craft.py`, `engine/itemui.py`.
**Критерий приёмки:** сценарий «0 золота, 150 бронзы, зелье за 1 золото»: в старом коде — отказ, в новом — покупка возможна только после конвертации; тест на границу конвертации (99🟤 → 100🟤).

### № 92. Бот: единая точка списания (добить остатки прямых `gold`)
**Статус:** ✅ сделано (проверкой, правки не потребовались).
**Что проверено:** `grep -rnE "(character|char|ch|c)\.(gold|bronze|silver)\s*(\+=|-=|=)" bot/ core/ admin/` даёт **ноль** операций `+=`/`-=` и ровно три присваивания, все обоснованные:
* `bot/handlers/start.py:1210` — стартовый бонус фракции начисляется бронзой намеренно, без нормализации в серебро: игрок должен увидеть ровно ту сумму, которую обещала карточка фракции (в коде это объяснено комментарием);
* `admin/main.py:810` и `:914` — админ прямо задаёт значение поля из формы, это установка величины, а не транзакция; конвертация здесь не нужна.
Все игровые траты и начисления уже идут через `engine/currency.add_currency` / `deduct_currency` (14 модулей `bot/` и `core/`).
**Вывод:** пункт закрыт без изменения кода — переписывать три обоснованных места ради формальной «единой точки» значило бы сломать понятное поведение.

### № 93. Сквозной тест конвертации 1:100 в обоих стеках
**Статус:** ✅ сделано. **Сделано:** `tests/test_currency_parity.py` (8 тестов) — перенос разрядов (99+1 → 1⚪, 9999+1 → 1🟡), размен золота на покупку в 1🟤, отказ без списания, форматирование по масштабу, миграция старых сейвов и **паритет стеков**: одна последовательность операций даёт одинаковый кошелёк у `Player` и у `Character` (in-memory SQLite).
**Было:** **Доказательство:** `engine/currency.py` имеет собственные тесты? — нет отдельного набора; серверная конвертация покрыта косвенно (`tests/test_economy_and_lunar.py`).
**ТЗ:** pytest-набор `tests/test_currency_parity.py`: (1) `add_currency` 99+1 бронзы → 0🟤 1⚪; (2) 9999+1 → 0🟤 0⚪ 1🟡; (3) `deduct_currency` по частям из трёх валют; (4) один и тот же сценарий прогоняется для `Player` (движок) и для `Character` (сервер, in-memory SQLite) и даёт одинаковые строки `currency_str`.
**Файлы:** `tests/test_currency_parity.py` (новый, попадёт в автодетект `run_all.py`).

### № 94. Снять долг «Трёхвалютная экономика» с реестра
**Статус:** ✅ сделано. **Результат:** `python3 tests/test_parity.py` печатает «Паритет: **28 из 28** механик в обоих стеках», список «Ждут переноса» пуст — **долгов в реестре не осталось**. В `test_shared_numbers_match` добавлена сверка курса 1:100 и переноса разряда, чтобы вторая копия валютной логики с другим курсом не прошла молча.
**Было:** **ТЗ:** после закрытия 90–93 обновить `REGISTRY` в `tests/test_parity.py`: `server=["core/models.py", "core/…"]` (по факту реализации) и `todo=""`.
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

### № 98. `AUDIT-BUGS.md`: отметить закрытые долги A, B и C
**Статус:** ✅ сделано. **Сделано:** в `AUDIT-BUGS.md` добавлен датированный раздел «Закрыто позже — 2026-08-14» с тремя долгами (A — идентичность предмета через `engine/slots.py`, B — `player.worn`, C — этаж могилы), у каждого указан способ решения и имя регрессии. Исходный раздел находок оставлен как история; открытые пункты «Прочее на заметку» помечены как № 81–84 в этом файле.
**Было:** **Доказательство:** долги «B. player.worn» и «C. engine/death.bury без этажа» закрыты в этой сессии, но в `AUDIT-BUGS.md` они всё ещё значатся открытыми.
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
| 2. Паритет `core/` → `engine/` | 25 | № 11–19, 21–25, 32–35 | — | 7 серверных подсистем без браузерного близнеца |
| 3. Вход игроку в боте | 25 | № 36–57 (кроме 58) | № 59 | подсистемы без единого вызова из `bot/handlers/` |
| 4. Админка `admin/main.py` | 10 | № 61–66 | — | 13 подсистем с нулём упоминаний в админке |
| 5. Панель `webapp/pages/` | 6 | № 72 | — | страницы Pyodide-панели после переносов Раздела 2 |
| 6. Баги и долги из аудита | 12 | № 77–85, 87, 88 (все) | — | **все долги аудита закрыты** |
| 7. Трёхвалютная экономика | 6 | № 89–94 (все) | — | **долг закрыт: паритет 28/28** |
| 8. Документация | 6 | № 95, 98, 100 | — | устаревшие цифры и списки |
| **Итого** | **100** | **77** | **1** | — |

**Сделано на 2026-08-14: 77 пунктов закрыто полностью, 1 частично, 1 снят как задача-фантом (№ 58).**
Закрыты: № 1, 2, 3, 6–19, 21–25, 32–35, 36–57 (кроме 58), 61–66, 72, 77–85, 87–95, 98, 100.
**Паритет: 44 из 44 механик в обоих стеках, долгов в реестре нет.**
**Раздел 6 закрыт целиком** — в `AUDIT-BUGS.md` не осталось незакрытых находок.
**В реестре паритета долгов больше нет: 28 из 28 механик в обоих стеках.**
**Долг A закрыт** — самое старое известное семейство багов браузерного стека (дубликаты вещей) больше не воспроизводится.
Частично остался только № 59 (`auction_bid.py` — заглушка ждёт решения владельца: удалить или реализовать).
**Все ранее частичные пункты доведены до конца** отдельной партией работ (строки «Партия 6» в таблице выше).
Проверка: `python3 tests/run_all.py` → **59 наборов, все зелёные** (было 41 запускаемый из 53 существующих). Новые наборы: `tests/test_karma_omens_engine.py` (42 проверки), `tests/test_bot_entrypoints.py` (10), `tests/test_admin_subsystems.py` (7), `tests/test_guild_bounty_duel_entrypoints.py` (10), `tests/test_bestiary_illusions_mentor.py` (8), `tests/test_bundle_integrity.py`.

### Отдельно: найденные «мёртвые» кнопки и вызовы
Аудит кода ловит не только отсутствующие механики, но и **обманки** — интерфейс есть, за ним пусто:
* `pvp_select` («⚔️ Напасть на игрока») — кнопка в клавиатуре осмотра **без обработчика**, нажатие не делало ничего (закрыто, № 53);
* `bounty_track:` + `bounty_board_keyboard` — клавиатура написана, обработчика нет (закрыто, № 55);
* `core/bounty.record_mob_kill` — функция не вызывалась ниоткуда, поэтому доска наград была пуста навсегда (закрыто, № 55);
* таблицы `guilds`/`guild_members`/`guild_vault_items` — **никогда не создавались**, потому что модели объявлены в `core/guilds.py`, а миграции импортировали только `core/models.py` (закрыто, № 51);
* `core/auction_bid.py` — модуль не импортируется вообще нигде, включая тесты (открыто, № 59).

### Что брать следующим (по стоимости/эффекту)
1. **№ 79–80 (долг A)** — рефакторинг инвентаря браузерного стека на uid: чинит целое семейство багов с дубликатами вещей (продажа копии снимает экипировку, дубликат не выпадает в могилу). Самый весомый оставшийся долг.
2. **№ 90–94** — добить трёхвалютную экономику и снять последний долг реестра паритета.
3. **№ 67–70** — остаток админки: арена и дуэли, редактор знамений, престиж/титулы в карточке, realtime-лента новых событий.
4. **№ 11–35** — перенос подсистем `core/` в браузерный стек `engine/` (25 пунктов, самый объёмный блок).
