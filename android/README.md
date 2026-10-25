# 📱 Shadow Lands — Android-приложение

Нативная Android-обёртка (WebView) над веб-панелью Shadow Lands со встроенным
**автообновлением через GitHub Releases**. Google Play не нужен.

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
  (например, свой Render/локальный сервер), есть кнопка сброса.
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

Сборку, выравнивание (`zipalign`) и подпись (`apksigner`) выполняет
GitHub Actions — шаблон workflow лежит в [`ci/android.yml`](ci/android.yml).
Локально Android SDK не требуется, чтобы получить рабочий APK.

> ⚠️ **Одноразовая активация CI.** Агент Arena не имеет права создавать
> файлы в `.github/workflows/`, поэтому workflow нужно один раз скопировать
> туда через веб-интерфейс GitHub — пошагово это описано в
> [`ci/README.md`](ci/README.md). Без этого шага автосборка релизов не работает.

## Как выпустить новую версию (для пользователя приложения)

1. Закоммитьте и запушьте изменения (веб-панель обновится на GitHub Pages
   сама, как и раньше).
2. Создайте релиз на GitHub с тегом вида `v1.0.1`:
   ```bash
   gh release create v1.0.1 --title "Shadow Lands 1.0.1" \
     --notes "Что нового в этой версии"
   ```
3. Workflow **Android APK** запустится автоматически (после одноразовой
   активации из [`ci/README.md`](ci/README.md)), соберёт APK и прикрепит
   его к релизу файлом `shadow-lands.apk` (10–15 минут, статус — вкладка
   Actions).
4. У всех пользователей при следующем запуске приложение само предложит
   обновиться. Версия берётся из тега: `v1.0.1` → `versionName 1.0.1`,
   `versionCode` — номер прогона workflow (всегда растёт, поэтому Android
   принимает обновление).

Собрать APK без релиза можно вручную: **Actions → Android APK → Run workflow**.
APK появится в артефактах прогона; если в поле `release_tag` указать тег
существующего релиза, APK будет прикреплён и к нему.

## Установка APK на телефон

1. Скачайте `shadow-lands.apk`:
   - из последнего релиза: <https://github.com/AlfaGideon/TG-MMO-RPG/releases>,
     либо
   - прямо из репозитория: файл `android/dist/shadow-lands.apk` (CI кладёт
     его туда при каждом релизе).
2. Откройте файл — Android попросит разрешить установку из браузера/файлового
   менеджера, подтвердите.
3. Дальше обновления ставятся через само приложение (один раз придётся
   разрешить «установку из неизвестных источников» для Shadow Lands).

## Локальная сборка (необязательно)

Через Android Studio: открыть папку `android/`, дождаться синхронизации,
**Build → Build Bundle(s) / APK(s) → Build APK(s)**.

Через командную строку (нужны JDK 17 и Android SDK с platform 34 /
build-tools 34.0.0):

```bash
cd android
./gradlew assembleRelease
# неподписанный APK:
# app/build/outputs/apk/release/app-release-unsigned.apk

# подпись тем же ключом, что и в CI:
$ANDROID_HOME/build-tools/34.0.0/zipalign -p -f 4 \
  app/build/outputs/apk/release/app-release-unsigned.apk aligned.apk
$ANDROID_HOME/build-tools/34.0.0/apksigner sign \
  --key keystore/release.key.pem --cert keystore/release.cert.pem \
  --out shadow-lands.apk aligned.apk
```

Для отладки на телефоне удобнее `./gradlew installDebug` — отладочная сборка
подписывается автоматически, но **на неё нельзя накатывать релизные обновления**:
сертификаты разные. Для теста автообновления используйте подписанный релизный APK.

## Структура

```
android/
├── app/
│   ├── build.gradle.kts
│   └── src/main/
│       ├── AndroidManifest.xml
│       ├── java/com/alfagideon/shadowlands/
│       │   ├── MainActivity.kt      # WebView, меню, диалоги настроек
│       │   ├── UpdateManager.kt     # проверка релизов, загрузка и установка APK
│       │   └── Prefs.kt             # SharedPreferences (URL, время проверки)
│       └── res/                     # тема, иконка, строки (RU), меню
├── keystore/                        # PEM-ключ подписи — см. keystore/README.md
├── gradle/wrapper/                  # Gradle 8.9 wrapper
├── build.gradle.kts                 # AGP 8.5.2 + Kotlin 1.9.24
└── settings.gradle.kts
```
