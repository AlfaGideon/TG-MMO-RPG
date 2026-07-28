# Shadow Lands — серверная админ-панель

> Карта админки для AI-сессий. Читать перед задачами в `admin/`.

## Технологии

- **FastAPI** — маршруты и API.
- **Jinja2** — шаблоны в `admin/templates/`.
- **Vanilla CSS** — `admin/static/style.css`.
- **Vanilla JS** — небольшие скрипты внутри шаблонов.

## Точка входа

```python
# admin/main.py
app = FastAPI(title="Shadow Lands Admin", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="admin/static"), name="static")
templates = Jinja2Templates(directory="admin/templates")
```

Запуск: `python launch.py` или `python -m admin.main`.

## Авторизация

- Владелец (direct access) — полные права, роль `None`.
- Выданные админы — вход по Telegram ID + пароль через `/admin-login`.
- Сессия — подписанная cookie `wa_session`.
- Права — `guard(request, cap)` вызывает `webauth.has_capability(...)`.
- Роли и точечные права определены в `engine/permissions.py`.

## Маршруты

| URL | Шаблон | Что делает | Право |
|---|---|---|---|
| `/` | `dashboard.html` | Сводка, последние бои | — |
| `/players` | `players.html` | Список персонажей | — |
| `/player/{id}` | `player_detail.html` | Карточка игрока | `view_players` |
| `/player/{id}/edit` | POST | Редактирование персонажа | `edit_players` |
| `/player/{id}/heal` | GET | Восстановить HP/MP | `heal_players` |
| `/player/{id}/give-item` | POST | Выдать предмет | `give_items` |
| `/player/{id}/grant-admin` | POST | Выдать доступ админу | `grant_admin` |
| `/items` | `items.html` | Предметы и магазин | — |
| `/item/{id}/edit` | `item_edit.html` | Редактор предмета | `manage_content` |
| `/battles` | `battles.html` | История боёв | — |
| `/map` | `players_map.html` | Карта игроков | — |
| `/settings` | `settings.html` | Токен, URL, бот | `settings` |
| `/content` | `content.html` | Хаб контента | `manage_content` |
| `/editor/world` | `editor_world.html` | Расположение локаций | `manage_content` |
| `/editor/locations` | `editor_locations.html` | Список локаций | `manage_content` |
| `/editor/location/{id}` | `editor_location.html` | Редактор локации | `manage_content` |
| `/editor/location/new` | `editor_location_new.html` | Создание локации | `manage_content` |
| `/editor/cell/{id}` | `editor_cell.html` | Редактор клетки | `manage_content` |
| `/editor/mobs` | `editor_mobs.html` | Мобы | `manage_content` |
| `/editor/quests` | `editor_quests.html` | Квесты | `manage_content` |
| `/editor/dungeons` | `editor_dungeons.html` | Подземелья | `manage_content` |
| `/editor/classes` | `editor_classes.html` | Классы | `manage_content` |
| `/editor/drops` | `editor_drops.html` | Таблицы лута | `manage_content` |
| `/editor/craft` | `editor_craft.html` | Крафт и заточка | `manage_content` |
| `/editor/spawns` | `editor_spawns.html` | Живая популяция мобов | `manage_content` |
| `/editor/instances` | `editor_instances.html` | Реестр экземпляров | `manage_content` |
| `/editor/auction` | `editor_auction.html` | Аукцион | `manage_content` |
| `/editor/events` | `editor_events.html` | События и реликвии | `manage_content` |
| `/editor/npcs` | `editor_npcs.html` | NPC на клетках | `manage_content` |
| `/instance/{id}` | `instance_detail.html` | Летопись экземпляра | `manage_content` |

## Шаблоны

- `base.html` — базовый layout: боковое меню, topbar, подключение `style.css` и общих скриптов.
- Все остальные шаблоны наследуют `base.html`.
- CSS-переменные определены в `:root` в `admin/static/style.css`.

## Компоненты UI (CSS-классы)

| Класс | Назначение |
|---|---|
| `.card` | Блок с рамкой и скруглением |
| `.stats-grid` / `.stat-box` | Стат-боксы на дашборде |
| `.content-hub-grid` / `.content-card` | Плитки в хабе контента |
| `.table-wrap` + `table` | Таблицы с горизонтальной прокруткой |
| `.badge` + `.badge-{rarity}` | Бейджи редкости/статуса |
| `.btn`, `.btn-primary`, `.btn-danger`, `.btn-sm` | Кнопки |
| `.form-grid`, `.field-row`, `.field-group` | Сетки форм |
| `.tabs`, `.tab-btn`, `.tab-panel` | Вкладки |
| `.inv-grid`, `.inv-card` | Инвентарь игрока |
| `.slot-grid`, `.slot-box` | Слоты экипировки |
| `.search-box` | Поля ввода/поиска |

## JS-хелперы в `base.html`

- `toggleSidebar(force)` — мобильное меню.
- `toggleGroup(id)` — сворачивание групп в боковом меню.
- `updateGitHeader(btn)` — кнопка «Обновить с GitHub».

## Частые паттерны

### Добавление нового экрана

1. Маршрут в `admin/main.py`.
2. Шаблон в `admin/templates/` с `{% extends "base.html" %}`.
3. Ссылка в `base.html` (или в `content.html`).
4. Проверка права через `guard(request, "...")`.
5. Обновить `admin/ADMIN_README.md`.

### Добавление формы

- Использовать `Form(...)` параметры.
- POST-обработчик возвращает `RedirectResponse(url=..., status_code=303)`.
- Для загрузки файлов — `UploadFile = File(None)`.

### Работа с БД

```python
async with async_session() as session:
    ...
    await session.commit()
```

## Известные зоны для улучшения

- Нет хлебных крошек в глубоких редакторах.
- Нет глобального поиска.
- Списки (`/players`, `/items`, `/editor/instances`) грузят всё сразу — нужна пагинация/поиск.
- Нет пагинации в таблицах.
- Нет массовых действий.
- `alert()` для уведомлений — лучше заменить toasts.
- Мобильная версия таблиц — превращать в карточки.
- `admin/main.py` большой — имеет смысл разбивать на `admin/routers/`.
