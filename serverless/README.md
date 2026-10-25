# Shadow Lands — Telegram Serverless (tgcloud)

Игровой срез проекта, переписанный на JavaScript под платформу **Telegram
Serverless**. Это отдельный стек: Python-код (`bot/`, `admin/`, `webapp/`,
`launch.py`) здесь не используется и не переносится — облако Telegram исполняет
только JS-модули в V8-изолятах.

## Почему так

Прежняя архитектура требовала постоянно работающего HTTP-сервера (Render/VPS),
которого у проекта нет: браузерная панель `webapp/` — это Pyodide во вкладке с
хранением в localStorage, она не может быть сервером для APK.

Telegram Serverless даёт сервер без хостинга:

- бот-хендлеры и endpoints исполняются платформой, платить/поддерживать VPS не нужно;
- данные — встроенная SQLite, персистентная между вызовами;
- Mini App хостится платформой на `https://app<id>.tgcloud.ai/`;
- авторизация — `initData`, которую Telegram проверяет **до** запуска endpoint
  (запрос без валидных initData получает 401, код даже не вызывается).

## Структура

```
serverless/
├── tgcloud.jsonc            # конфиг: статика Mini App = папка web/
├── package.json             # npm test / deploy / migrate
├── tgcloud/
│   ├── schema.js            # таблицы SQLite (без внешних ключей — требование платформы)
│   ├── lib/
│   │   ├── config.js        # MINI_APP_URL, BOT_USERNAME, константы, классы
│   │   ├── rng.js           # детерминированный ГПСЧ (юнит-тесты)
│   │   ├── progression.js   # чистая математика: урон, крит, опыт, побег
│   │   ├── world.js         # сид мира, респавн мобов/сундуков, сетка
│   │   ├── character.js     # пользователи, создание героя, доступ по initData
│   │   ├── battle.js        # бой как строка БД (памяти между вызовами нет)
│   │   └── state.js         # сборка единого контракта состояния для экрана
│   ├── handlers/
│   │   ├── message.js       # /start, /app, /help
│   │   └── callback_query.js
│   └── endpoints/           # POST /api/<name>, вызываются только из Mini App
│       ├── getProfile.js  move.js  inspect.js  rest.js
│       ├── battleStart.js  battleAttack.js  battleFlee.js
│       └── equip.js  unequip.js  useItem.js
└── web/                     # статика Mini App (ванильный JS, без сборки)
    ├── index.html
    ├── app.js               # все запросы через Telegram.WebApp.Serverless.call
    ├── player.css
    └── branding/start_ru.png
```

## Деплой (выполняет владелец бота — нужен доступ к BotFather)

Требуется Node.js 18+ и бот, у которого в BotFather включён Serverless.

### Шаг 1. BotFather

1. Открыть [@BotFather](https://t.me/BotFather) → выбрать бота →
   **Bot Settings → Serverless** → включить.
2. Запомнить имя бота (`@username`) — оно нужно для `BOT_USERNAME`.

### Шаг 2. Привязка проекта и первый деплой

Из папки `serverless/` выполнить (логин откроет браузер с подтверждением):

```bash
cd serverless
npx tgcloud@latest login
npx tgcloud@latest push
```

CLI напечатает адрес Mini App вида `https://app1234567890.tgcloud.ai/` и покажет
ожидающие миграции БД. Применить их:

```bash
npx tgcloud@latest migrate
```

### Шаг 3. Прописать адрес и имя бота

Открыть `tgcloud/lib/config.js` и заменить две константы на свои значения:

```js
export const MINI_APP_URL = 'https://app1234567890.tgcloud.ai/';
export const BOT_USERNAME = 'ваш_бот_без_собачки';
```

После этого запушить ещё раз — кнопка Web App в `/start` заработает:

```bash
npx tgcloud@latest push
```

### Шаг 4. Проверка

1. В Telegram отправить боту `/start` — придёт приветствие и кнопка
   «🎮 Открыть Shadow Lands».
2. Нажать кнопку: откроется Mini App, персонаж создаётся автоматически у
   лагерного костра. D-pad двигает по карте, кнопка «Атаковать» запускает бой,
   лут и опыт сохраняются в облаке.
3. Локальная проверка endpoint без Telegram (ctx передаётся непроверенным,
   только для отладки):

```bash
npx tgcloud@latest run endpoints/getProfile '{}' --ctx '{ "initData": { "user": { "id": 1 } } }'
```

## Тесты

Юнит-тесты покрывают чистую математику (RNG, урон, крит, опыт, побег,
характеристики) — модули без зависимости от платформенного `sdk`:

```bash
cd serverless
npm test
```

## Про standalone-APK

Прямые вызовы `/api/*` из внешнего WebView невозможны: платформенный гейт
проверяет initData до исполнения кода и возвращает 401. Встраивать в APK
управляющий секрет `app<id>:<secret>` нельзя — это ключ от деплоя и БД, он
легко извлекается из распакованного APK.

Официальный **Telegram Login SDK for Android**
(`org.telegram:login-sdk`, BotFather → Web Login → Native Login) проверен по
исходникам: он выдаёт только подписанный JWT `idToken` для входа на собственный
бэкенд. Mini App initData он не выпускает, поэтому гейт tgcloud-endpoints этим
токеном не открывается.

Поэтому APK остаётся **брендированным лаунчером**: нативный экран с кнопкой,
которая открывает дип-линк `https://t.me/<бот>?startapp=enter` — Telegram
запускает Mini App с настоящими initData, и весь игровой функционал доступен.
Переделка player-flavor под эту схему — следующий этап, после подтверждённого
деплоя Mini App.

## Границы MVP

- одна локация 8×8 (Сумеречные руины), 5 типов мобов, 7 предметов;
- нет: торговца, крафта, дома, аукциона, лидербордов, нескольких локаций,
  выбора класса при старте (по умолчанию Воин);
- перенос прогресса из браузерной панели `webapp/` не автоматический — формат
  localStorage и SQLite различается, нужен отдельный скрипт импорта по JSON.
