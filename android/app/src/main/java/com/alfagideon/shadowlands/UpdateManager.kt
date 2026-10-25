package com.alfagideon.shadowlands

import android.app.DownloadManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.Settings
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

/**
 * Автообновление через GitHub Releases.
 *
 * 1. Дёргаем API: /repos/AlfaGideon/TG-MMO-RPG/releases/latest
 * 2. Сравниваем тег релиза с versionName приложения (семантическое сравнение)
 * 3. Качаем APK-ассет через DownloadManager
 * 4. Открываем системный установщик (FileProvider + REQUEST_INSTALL_PACKAGES)
 */
class UpdateManager(private val activity: MainActivity) {

    private data class Release(
        val tag: String,
        val apkUrl: String?,
        val notes: String,
        val htmlUrl: String,
    )

    private val executor = Executors.newSingleThreadExecutor()
    private var downloadId = -1L
    private var pendingInstall: File? = null

    private val downloadReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            val id = intent?.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID, -1L) ?: return
            if (id != downloadId) return
            val manager = activity.getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
            val cursor = manager.query(DownloadManager.Query().setFilterById(id)) ?: return
            cursor.use {
                if (!it.moveToFirst()) return
                val status = it.getInt(it.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS))
                if (status == DownloadManager.STATUS_SUCCESSFUL) {
                    pendingInstall?.let(::installApk)
                } else {
                    val reason = it.getInt(it.getColumnIndexOrThrow(DownloadManager.COLUMN_REASON))
                    Toast.makeText(
                        activity,
                        activity.getString(R.string.update_download_failed, reason),
                        Toast.LENGTH_LONG
                    ).show()
                }
            }
        }
    }

    fun register() {
        // На Android 13+ системный широковещательный приёмник требует явный флаг.
        ContextCompat.registerReceiver(
            activity,
            downloadReceiver,
            IntentFilter(DownloadManager.ACTION_DOWNLOAD_COMPLETE),
            ContextCompat.RECEIVER_EXPORTED
        )
    }

    fun unregister() {
        runCatching { activity.unregisterReceiver(downloadReceiver) }
    }

    /** Автопроверка при старте, но не чаще одного раза в [CHECK_INTERVAL]. */
    fun autoCheck() {
        val now = System.currentTimeMillis()
        if (now - Prefs.lastCheck(activity) < CHECK_INTERVAL) return
        check(manual = false)
    }

    fun manualCheck() = check(manual = true)

    private fun check(manual: Boolean) {
        if (manual) {
            Toast.makeText(activity, R.string.check_update, Toast.LENGTH_SHORT).show()
        }
        executor.execute {
            val release = try {
                fetchLatest()
            } catch (e: Exception) {
                null
            }
            Prefs.setLastCheck(activity, System.currentTimeMillis())
            activity.runOnUiThread {
                when {
                    release == null -> if (manual) {
                        Toast.makeText(activity, R.string.update_check_failed, Toast.LENGTH_LONG).show()
                    }
                    isNewer(release.tag) -> showUpdateDialog(release)
                    manual -> Toast.makeText(
                        activity,
                        activity.getString(R.string.update_up_to_date, currentVersion()),
                        Toast.LENGTH_LONG
                    ).show()
                }
            }
        }
    }

    private fun fetchLatest(): Release? {
        val connection = (URL(LATEST_URL).openConnection() as HttpURLConnection).apply {
            connectTimeout = 15_000
            readTimeout = 15_000
            setRequestProperty("Accept", "application/vnd.github+json")
            setRequestProperty("User-Agent", "ShadowLands-Android")
        }
        connection.inputStream.use { stream ->
            val json = JSONObject(stream.bufferedReader().readText())
            val tag = json.optString("tag_name").ifBlank { return null }
            var apkUrl: String? = null
            var fallbackUrl: String? = null
            val assets = json.optJSONArray("assets")
            if (assets != null) {
                for (i in 0 until assets.length()) {
                    val asset = assets.getJSONObject(i)
                    val name = asset.optString("name")
                    if (!name.endsWith(".apk", ignoreCase = true)) continue
                    // Приоритет — ассет именно этого издания (admin/player),
                    // первый попавшийся .apk оставляем запасным вариантом
                    // для совместимости со старыми релизами.
                    if (name.equals(BuildConfig.RELEASE_ASSET, ignoreCase = true)) {
                        apkUrl = asset.optString("browser_download_url")
                        break
                    }
                    if (fallbackUrl == null) {
                        fallbackUrl = asset.optString("browser_download_url")
                    }
                }
            }
            if (apkUrl == null) apkUrl = fallbackUrl
            return Release(
                tag = tag,
                apkUrl = apkUrl,
                notes = json.optString("body").take(4_000),
                htmlUrl = json.optString("html_url"),
            )
        }
    }

    private fun isNewer(tag: String): Boolean =
        compareVersions(normalize(tag), normalize(currentVersion())) > 0

    private fun currentVersion(): String =
        runCatching {
            @Suppress("DEPRECATION")
            activity.packageManager.getPackageInfo(activity.packageName, 0).versionName
        }.getOrNull() ?: "1.0.0"

    private fun showUpdateDialog(release: Release) {
        val message = buildString {
            append("Доступна версия ").append(release.tag).append("\n\n")
            append(release.notes.ifBlank { "Обновление содержит исправления и улучшения." })
            if (release.apkUrl == null) {
                append("\n\nAPK ещё не прикреплён к релизу — откроется страница загрузки.")
            }
        }
        AlertDialog.Builder(activity)
            .setTitle(R.string.update_available)
            .setMessage(message)
            .setPositiveButton(R.string.update_install) { _, _ ->
                if (release.apkUrl != null) download(release) else openUrl(release.htmlUrl)
            }
            .setNeutralButton(R.string.update_open_page) { _, _ -> openUrl(release.htmlUrl) }
            .setNegativeButton(R.string.update_later, null)
            .setCancelable(true)
            .show()
    }

    private fun download(release: Release) {
        val url = release.apkUrl ?: return
        val dir = activity.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
            ?: activity.filesDir
        dir.mkdirs()
        // Имя файла наследуем от ассета издания: shadow-lands.apk /
        // shadow-lands-player.apk (+ нормализованный тег версии).
        val base = BuildConfig.RELEASE_ASSET.removeSuffix(".apk")
        val target = File(dir, "$base-${normalize(release.tag)}.apk")
        if (target.exists()) target.delete()
        pendingInstall = target

        val request = DownloadManager.Request(Uri.parse(url))
            .setTitle("Shadow Lands ${release.tag}")
            .setDescription(activity.getString(R.string.update_downloading))
            .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            .setAllowedOverMetered(true)
            .setAllowedOverRoaming(true)
            .setDestinationUri(Uri.fromFile(target))

        val manager = activity.getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
        downloadId = manager.enqueue(request)
        Toast.makeText(activity, R.string.update_download_started, Toast.LENGTH_LONG).show()
    }

    fun installApk(file: File) {
        // Android 8+: нужно разрешение на установку из неизвестного источника.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
            !activity.packageManager.canRequestPackageInstalls()
        ) {
            pendingInstall = file
            activity.startActivity(
                Intent(
                    Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:${activity.packageName}")
                )
            )
            Toast.makeText(activity, R.string.update_allow_unknown, Toast.LENGTH_LONG).show()
            return
        }
        val uri = FileProvider.getUriForFile(
            activity,
            "${activity.packageName}.fileprovider",
            file
        )
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        activity.startActivity(intent)
    }

    /** Повторная попытка установки после того, как пользователь выдал разрешение в настройках. */
    fun resumePendingInstall() {
        val file = pendingInstall ?: return
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O ||
            activity.packageManager.canRequestPackageInstalls()
        ) {
            installApk(file)
        }
    }

    private fun openUrl(url: String) {
        if (url.isBlank()) return
        runCatching { activity.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) }
    }

    companion object {
        private const val REPO = "AlfaGideon/TG-MMO-RPG"
        private const val LATEST_URL = "https://api.github.com/repos/$REPO/releases/latest"
        private const val CHECK_INTERVAL = 6L * 60 * 60 * 1000 // 6 часов

        fun normalize(version: String): String =
            version.trim().removePrefix("v").removePrefix("V")

        /** Семантическое сравнение: 1.10.0 > 1.9.1; нечисловые куски считаются нулём. */
        fun compareVersions(a: String, b: String): Int {
            val partsA = a.split(".")
            val partsB = b.split(".")
            val size = maxOf(partsA.size, partsB.size)
            for (i in 0 until size) {
                val x = partsA.getOrNull(i)?.toIntOrNull() ?: 0
                val y = partsB.getOrNull(i)?.toIntOrNull() ?: 0
                if (x != y) return x - y
            }
            return 0
        }
    }
}
