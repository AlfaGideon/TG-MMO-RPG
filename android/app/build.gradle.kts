plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Версия передаётся из CI (-PappVersion / -PappVersionCode),
// при локальной сборке используются значения по умолчанию.
val appVersion: String = (project.findProperty("appVersion") as String?) ?: "1.0.0"
val appVersionCode: Int =
    (project.findProperty("appVersionCode") as String?)?.toIntOrNull() ?: 1

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

    buildTypes {
        release {
            // Подпись выполняется в CI через apksigner (PEM-ключ в keystore/),
            // поэтому здесь сборка остаётся без встроенного signingConfig.
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
