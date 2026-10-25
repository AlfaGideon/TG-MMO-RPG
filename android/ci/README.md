# CI для сборки APK — два независимых workflow

В проекте два приложения и два отдельных workflow-файла, которые **не
зависят друг от друга**:

| Workflow | Файл в `.github/workflows/` | Что собирает | Ассет релиза | Копия в репо |
|---|---|---|---|---|
| Android APK (существующий, не трогаем) | `android.yml` | flavor `admin` | `shadow-lands.apk` | `android/dist/shadow-lands.apk` |
| Android APK Player (новый) | `android-player.yml` | flavor `player` | `shadow-lands-player.apk` | `android/dist/shadow-lands-player.apk` |

Шаблоны лежат не в `.github/workflows/`, а здесь, потому что автоматический
агент Arena не имеет права создавать workflow-файлы через API (правило
безопасности GitHub). Первый workflow у вас уже активирован — **его менять
не нужно**. Ниже только добавление второго.

## Активация workflow игрока (2 минуты, без клонирования)

1. Откройте в браузере:
   **<https://github.com/AlfaGideon/TG-MMO-RPG/new/main/.github/workflows>**
2. В поле имени файла введите: `android-player.yml`
   (именно новое имя — `android.yml` не открывайте и не перезаписывайте).
3. Откройте [`android-player.yml`](android-player.yml) в репозитории,
   нажмите **Raw**, скопируйте всё содержимое и вставьте в редактор на GitHub.
4. Нажмите **Commit changes… → Commit changes**.

Готово. Теперь:

- каждый новый **релиз** (тег `vX.Y.Z`) запускает **оба** workflow:
  существующий `Android APK` собирает админский APK, новый
  `Android APK Player` — игровой. К релизу прикрепляются оба файла,
  `shadow-lands.apk` и `shadow-lands-player.apk`, и оба кладутся в
  `android/dist/`;
- вручную игровая сборка запускается на вкладке
  **Actions → Android APK Player → Run workflow** (APK будет в артефакте
  `shadow-lands-player-apk`; если указать `release_tag`, он прикрепится и к
  существующему релизу).

## Почему существующий workflow продолжит работать без правок

С вводом flavor'ов Gradle раскладывает APK по
`outputs/apk/<flavor>/release/`, тогда как старый `android.yml` ищет файл в
`outputs/apk/release/`. Чтобы не менять ни строчки в старом workflow, в
`app/build.gradle.kts` добавлена задача `stageLegacyAdminApk`: после
`assembleAdminRelease` она дублирует админский APK по прежнему пути
`outputs/apk/release/`. Старый workflow находит его как раньше.

## Параллельный запуск двух workflow на один релиз

Оба workflow подписывают одним и тем же keystore (это нормально — package
у приложений разные) и на финальном шаге коммитят свои APK в `main`.
Файлы у них разные, поэтому конфликтов содержимого нет, а workflow игрока
перед push забирает свежий `main` через `rebase` и повторяет push до трёх
раз. Если в редком случае красным загорится шаг коммита у старого
workflow — ассет релиза к этому моменту уже загружен, достаточно нажать
**Re-run failed jobs**.

## Первая сборка после активации

Создайте релиз (можно с веб-страницы
[Releases → Draft a new release](https://github.com/AlfaGideon/TG-MMO-RPG/releases/new),
тег вида `v1.2.0`). Оба workflow запустятся сами, и через 10–15 минут в
активах релиза появятся оба APK. Дальше каждое приложение обновляется само:
`UpdateManager` матчит ассет по имени своего издания
(`shadow-lands.apk` / `shadow-lands-player.apk`).

> Если позже будете менять сам workflow, правки уже скопированного
> `.github/workflows/android-player.yml` можно коммитить обычным путём —
> ограничение действует только на создание нового workflow-файла.
