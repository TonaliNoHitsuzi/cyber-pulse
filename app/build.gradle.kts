plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.google.devtools.ksp")
}

android {
    namespace = "com.nanshan.classroommonitor"
    compileSdk = 34

    defaultConfig {
        // 赛博把脉（与原AGC包名解耦）
        applicationId = "com.pulse.cyberpulse"
        minSdk = 23
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0-pulse"
    }

    signingConfigs {
        create("classroom") {
            val ks = rootProject.file("keystore/classroom.jks")
            if (ks.exists()) {
                storeFile = ks
                storePassword = "classroom2026"
                keyAlias = "classroom"
                keyPassword = "classroom2026"
            }
        }
    }

    buildTypes {
        debug {
            versionNameSuffix = ""
            if (rootProject.file("keystore/classroom.jks").exists()) {
                signingConfig = signingConfigs.getByName("classroom")
            }
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }

        release {
            if (rootProject.file("keystore/classroom.jks").exists()) {
                signingConfig = signingConfigs.getByName("classroom")
            }
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation(platform("androidx.compose:compose-bom:2024.10.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.foundation:foundation")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    implementation("org.nanohttpd:nanohttpd:2.3.1")

    implementation("androidx.room:room-runtime:2.6.1")
    implementation("androidx.room:room-ktx:2.6.1")
    ksp("androidx.room:room-compiler:2.6.1")

    debugImplementation("androidx.compose.ui:ui-tooling")
}
