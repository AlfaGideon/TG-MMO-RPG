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
val keystoreFilePath = project.findProperty("keystoreFile") as String?
val keystorePassword = (project.findProperty("keystorePassword") as String?) ?: ""
val keyAlias = (project.findProperty("keyAlias") as String?) ?: "shadowlands"
val keyPassword = (project.findProperty("keyPassword") as String?) ?: keystorePassword

android {
    namespace = "com.alfagideon.shadowlands"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.alfagideon.shadowlands"
        minSdk = 24
        targetSdk = 34
        versionCode = appVersionCode
        versionName = appVersion
        vectorDrawables.useSupportLibrary = true
    }

    signingConfigs {
        if (keystoreFilePath != null) {
            create("release") {
                storeFile = file(keystoreFilePath)
                storePassword = keystorePassword
                this.keyAlias = keyAlias
                keyPassword = keyPassword
            }
        }
    }

    buildTypes {
        release {
            // Gradle сам подпишет APK и сделает zipalign, если передан keystore.
            if (keystoreFilePath != null) {
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

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.swiperefreshlayout:swiperefreshlayout:1.1.0")
}
