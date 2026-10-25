plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Версия передаётся из CI (-PappVersion / -PappVersionCode),
// при локальной сборке используются значения по умолчанию.
val appVersion: String = (project.findProperty("appVersion") as String?) ?: "1.0.0"
val appVersionCode: Int =
    (project.findProperty("appVersionCode") as String?)?.toIntOrNull() ?: 1

// Подпись релиза: в CI путь к PKCS12-keystore передаётся через -PkeystoreFile.
// Без этих свойств (локальная сборка без ключа) release остаётся неподписанным.
// ВАЖНО: имена внешних переменных не должны совпадать со свойствами
// SigningConfig (keyPassword/keyAlias/storePassword) — иначе внутри
// create("release") { ... } правое имя резолвится в собственный геттер
// конфига (null), а не во внешнюю val, и AGP падает с NPE на packageRelease.
val ksFile = project.findProperty("keystoreFile") as String?
val ksStorePassword = (project.findProperty("keystorePassword") as String?) ?: ""
val ksKeyAlias = (project.findProperty("keyAlias") as String?) ?: "shadowlands"
val ksKeyPassword = (project.findProperty("keyPassword") as String?) ?: ksStorePassword

android {
    namespace = "com.alfagideon.shadowlands"
    compileSdk = 34

    defaultConfig {
        minSdk = 24
        targetSdk = 34
        versionCode = appVersionCode
        versionName = appVersion
        vectorDrawables.useSupportLibrary = true
    }

    // Два издания одного WebView-клиента:
    //  * admin  — панель управления (исходное приложение, пакет ...shadowlands);
    //  * player — игровой клиент без админ-разделов: грузит /player/, имеет
    //             отдельный package (ставится рядом) и свой APK-ассет в релизе.
    flavorDimensions += "edition"
    productFlavors {
        create("admin") {
            dimension = "edition"
            applicationId = "com.alfagideon.shadowlands"
            buildConfigField(
                "String", "DEFAULT_URL",
                "\"https://alfagideon.github.io/TG-MMO-RPG/\""
            )
            buildConfigField("String", "RELEASE_ASSET", "\"shadow-lands.apk\"")
        }
        create("player") {
            dimension = "edition"
            applicationId = "com.alfagideon.shadowlands.player"
            // Тот же хост, что у админ-издания, но игровой раздел SPA.
            // Боевой адрес сервера игрок может сменить в меню «Адрес сервера».
            buildConfigField(
                "String", "DEFAULT_URL",
                "\"https://alfagideon.github.io/TG-MMO-RPG/player/\""
            )
            buildConfigField("String", "RELEASE_ASSET", "\"shadow-lands-player.apk\"")
        }
    }

    buildFeatures {
        buildConfig = true
    }

    signingConfigs {
        if (ksFile != null) {
            create("release") {
                storeFile = file(ksFile)
                storeType = "PKCS12"
                storePassword = ksStorePassword
                keyAlias = ksKeyAlias
                keyPassword = ksKeyPassword
            }
        }
    }

    buildTypes {
        release {
            // Gradle сам подпишет APK и сделает zipalign, если передан keystore.
            if (ksFile != null) {
                signingConfig = signingConfigs.getByName("release")
            }
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

// ── Совместимость с исходным CI (.github/workflows/android.yml) ────────
// Первый workflow не меняем: он запускает assembleRelease и ищет APK в
// outputs/apk/release/. С появлением flavor'ов варианты переезжают в
// outputs/apk/<flavor>/release/, поэтому дублируем admin-APK по старому
// пути. Новый workflow игрока читает свой путь outputs/apk/player/release/.
tasks.register<Copy>("stageLegacyAdminApk") {
    val root = layout.buildDirectory.get().asFile
    from("$root/outputs/apk/admin/release") { include("*.apk") }
    into("$root/outputs/apk/release")
}
tasks.matching { it.name == "assembleAdminRelease" }.configureEach {
    finalizedBy("stageLegacyAdminApk")
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.swiperefreshlayout:swiperefreshlayout:1.1.0")
}
