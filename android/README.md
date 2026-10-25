# 📱 Shadow Lands — Android-приложения

Нативная Android-обёртка (WebView) над веб-частью Shadow Lands со встроенным
**автообновлением через GitHub Releases**. Google Play не нужен.

## Два издания (product flavors)

Один код и одна WebView-обёртка собираются в два независимых приложения —
они ставятся рядом, у них разные package и точки входа:

| Издание  | package                              | Стартовый путь        | APK в релизе                | Для кого |
|----------|--------------------------------------|-----------------------|-----------------------------|----------|
| `admin`  | `com.alfagideon.shadowlands`         | `/` (панель)          | `shadow-lands.apk`          | Администрация |
| `player` | `com.alfagideon.shadowlands.player`  | `/player/ (игра)      | `shadow-lands-player.apk`   | Игроки |

Игровое издание не содержит админ-разделов: оно открывает только мобильный
SPA (`playerapp/`), вход в него — по коду из бота (`/app`) или автоматически
через Telegram Mini App. Герой, инвентарь и прогресс общие с ботом: и APK,
и бот работают с одной серверной БД. `UpdateManager` каждого издания
скачивает именно свой ассет релиза (матчинг по имени файла), поэтому
автообновления двух приложений не путаются.

## Что умеет приложение

- Открывает веб-версию панели (`https://alfagideon.github.io/TG-MMO-RPG/`)
  в полноэкранном WebView: JavaScript, DOM storage, WASM/Pyodide, загрузка
  файлов через `<input type="file">`, pull-to-refresh, кнопки «Назад» и
  «На главную».
- **Автообновление**: при запуске (не чаще раза в 6 часов) и вручную через
  меню «Проверить обновления» опрашивает GitHub API, сравнивает тег последнего
  релиза с версией приложения, скачивает APK-ассет и запускает системный
  установщик.
- **Свой сервер**: в меню «Адрес сервера» можно указать любой http(s)-адрес
  (например, свой Render/локальный сервер), есть кнопка сброса. В издании
  player путь `/player/` дописывается автоматически (`Prefs.canonicalize`),
  в admin открывается введённый корень как есть.
- Внешние ссылки (`tg:`, `mailto:`, `intent:`) открываются в соответствующих
  приложениях телефона.

Технические параметры: `minSdk 24` (Android 7.0+), `targetSdk 34`, Kotlin,
AndroidX + Material 3, package `com.alfagideon.shadowlands`.

## Как это работает

```
Запуск приложения
   │
   ├─► WebView грузит сохранённый URL (по умолчанию GitHub Pages)
   │
   └─► UpdateManager.autoCheck()
         GET https://api.github.com/repos/AlfaGideon/TG-MMO-RPG/releases/latest
         │
         ├─ версия релиза > versionName ──► диалог «Доступно обновление»
         │                                    │
         │                                    ├─ DownloadManager качает *.apk
         │                                    └─ FileProvider + системный установщик
         │                                         (один раз спросит разрешение
         │                                          на установку из источника)
         └─ версия та же ──► молча (или тост при ручной проверке)
```

Сборку, выравнивание (`zipalign`) и подпись (`apksigner`) выполняют
GitHub Actions — два независимых workflow под два издания:
[`ci/android.yml`](ci/android.yml) (админский, уже активен) и
[`ci/android-player.yml`](ci/android-player.yml) (игровой, активируется
один раз). Локально Android SDK не требуется, чтобы получить рабочий APK.

> ⚠️ **Одноразовая активация workflow игрока.** Существующий
> `.github/workflows/android.yml` менять не нужно — благодаря Gradle-мостику
> `stageLegacyAdminApk` он по-прежнему собирает админский APK без правок.
> Нужно лишь создать НОВЫЙ файл `.github/workflows/android-player.yml`
> из шаблона [`ci/android-player.yml`](ci/android-player.yml) — пошагово
> это описано в [`ci/README.md`](ci/README.md).

## Как выпустить новую версию (для пользователя приложения)

1. Закоммитьте и запушьте изменения (веб-панель обновится на GitHub Pages
   сама, как и раньше).
2. Создайте релиз на GitHub с тегом вида `v1.0.1`:
   ```bash
   gh release create v1.0.1 --title "Shadow Lands 1.0.1" \
     --notes "Что нового в этой версии"
   ```
3. На релиз автоматически запустятся **два независимых workflow**:
   **Android APK** (уже активен) соберёт админский `shadow-lands.apk`,
   **Android APK Player** (после одноразовой активации из
   [`ci/README.md`](ci/README.md)) — игровой `shadow-lands-player.apk`.
   Оба файла прикрепятся к релизу и лягут в `android/dist/` (10–15 минут,
   статус — вкладка Actions).
4. У всех пользователей при следующем запуске приложение само предложит
   обновиться — каждое издание матчит свой ассет. Версия берётся из тега:
   `v1.0.1` → `versionName 1.0.1`, `versionCode` — номер прогона workflow
   (всегда растёт, поэтому Android принимает обновление).

Собрать APK без релиза можно вручную: **Actions → Android APK Player →
Run workflow** (для игрока) или **Android APK → Run workflow** (для админки).
APK появится в артефактах прогона; если в поле `release_tag` указать тег
существующего релиза, APK будет прикреплён и к нему.

## Установка APK на телефон

1. Скачайте нужный APK:
   - **игрокам** — `shadow-lands-player.apk`;
   - **администрации** — `shadow-lands.apk`;
   - из последнего релиза: <https://github.com/AlfaGideon/TG-MMO-RPG/releases>,
     либо прямо из репозитория: файлы в `android/dist/` (CI кладёт их туда
     при каждом релизе).
2. Откройте файл — Android попросит разрешить установку из браузера/файлового
   менеджера, подтвердите.
3. Дальше обновления ставятся через само приложение (один раз придётся
   разрешить «установку из неизвестных источников» для Shadow Lands).
   Два издания можно держать установленными одновременно — пакеты разные.

### Вход в игровое издание

1. Откройте бота и отправьте команду `/app` — бот пришлёт одноразовый
   6-значный код (живёт 10 минут) и кнопку Mini App.
2. В приложении `Shadow Lands — Игра` введите код на экране входа.
   Внутри Telegram Mini App вход происходит автоматически, без кода.
3. Если сервер развёрнут не по адресу по умолчанию — откройте меню
   «Адрес сервера» и введите **корень** вашего сервера, например
   `https://shadow-lands.onrender.com`. Дописывать `/player/` не нужно:
   издание player само добавит этот путь (поле `ENTRY_PATH`), а старые
   сохранённые адреса нормализуются при следующем запуске.

## Локальная сборка (необязательно)

Через Android Studio: открыть папку `android/`, дождаться синхронизации,
**Build → Build Bundle(s) / APK(s) → Build APK(s)**.

Через командную строку (нужны JDK 17 и Android SDK с platform 34 /
build-tools 34.0.0):

```bash
cd android

# 1. собираем PKCS12-keystore из PEM-пары (пароль: shadowlands)
openssl pkcs12 -export \
  -inkey keystore/release.key.pem \
  -in keystore/release.cert.pem \
  -out keystore/release.p12 \
  -name shadowlands -password pass:shadowlands

# 2. Gradle сам подпишет APK и сделает zipalign.
#    Оба издания сразу:
./gradlew assembleAdminRelease assemblePlayerRelease \
  -PkeystoreFile="$PWD/keystore/release.p12" \
  -PkeystorePassword=shadowlands \
  -PkeyAlias=shadowlands \
  -PkeyPassword=shadowlands
# готовые APK:
# app/build/outputs/apk/admin/release/app-admin-release.apk
# app/build/outputs/apk/player/release/app-player-release.apk
#
# по одному: assembleAdminRelease | assemblePlayerRelease,
# отладочные:  installAdminDebug | installPlayerDebug
```

Без `-PkeystoreFile` собирается неподписанный `app-release-unsigned.apk`
(так делает только CI до шага конвертации ключа).

Для отладки на телефоне удобнее `./gradlew installDebug` — отладочная сборка
подписывается автоматически, но **на неё нельзя накатывать релизные обновления**:
сертификаты разные. Для теста автообновления используйте подписанный релизный APK.

## Иконка приложения

Иконка — это брендовый логотип `admin/static/branding/start_ru.png`
(тот же баннер, что бот показывает в Telegram при `/start`), уменьшенный
под все плотности экрана. Никаких векторных заглушек: картинка используется
целиком, без кропов.

Перегенерировать после замены исходного логотипа (нужен Pillow):

```bash
python3 tools/build_android_icons.py
```

Скрипт кладёт PNG в `app/src/main/res/mipmap-*` и фон адаптивной иконки
(API 26+) в `mipmap-xxxhdpi/ic_launcher_background.png`; маску (круг,
сквиркл) применяет система. Веб-копии логотипа (favicon, картинка в сайдбаре
панели) лежат в `webapp/static/brand-logo.png` и `favicon-*.png`.

## Структура

```
android/
├── app/
│   ├── build.gradle.kts            # flavorDimensions "edition": admin + player
│   └── src/
│       ├── main/                   # общий код и ресурсы обоих изданий
│       │   ├── AndroidManifest.xml
│       │   ├── java/com/alfagideon/shadowlands/
│       │   │   ├── MainActivity.kt   # WebView, меню, диалоги настроек
│       │   │   ├── UpdateManager.kt  # проверка релизов, загрузка своего APK
│       │   │   └── Prefs.kt          # SharedPreferences (URL, время проверки)
│       │   └── res/                  # тема, иконка, общие строки (RU), меню
│       ├── admin/res/values/strings.xml  # app_name/about_text издания admin
│       └── player/res/values/strings.xml # app_name/about_text издания player
├── ci/
│   ├── android.yml                  # шаблон активного workflow admin (НЕ меняем)
│   ├── android-player.yml           # шаблон нового workflow player (активация в README)
│   └── README.md                    # пошаговая активация второго workflow
├── keystore/                        # PEM-ключ подписи — см. keystore/README.md
├── gradle/wrapper/                  # Gradle 8.9 wrapper
├── build.gradle.kts                 # AGP 8.5.2 + Kotlin 1.9.24 + мостик stageLegacyAdminApk
└── settings.gradle.kts
```

Различия изданий заданы в `productFlavors` (`app/build.gradle.kts`):
`applicationId`, `BuildConfig.DEFAULT_URL` (корень панели или `/player/`)
и `BuildConfig.RELEASE_ASSET` (имя APK, который ищет автообновление).
