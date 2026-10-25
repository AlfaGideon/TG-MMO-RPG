package com.alfagideon.shadowlands

import android.content.Context

/** Хранилище настроек приложения: адрес веб-панели и время последней проверки обновлений. */
object Prefs {
    private const val FILE = "shadowlands_prefs"
    private const val KEY_URL = "server_url"
    private const val KEY_LAST_CHECK = "last_update_check"

    /** По умолчанию — статическая сборка на GitHub Pages этого репозитория. */
    const val DEFAULT_URL = "https://alfagideon.github.io/TG-MMO-RPG/"

    fun getUrl(context: Context): String =
        prefs(context).getString(KEY_URL, DEFAULT_URL) ?: DEFAULT_URL

    fun setUrl(context: Context, url: String) {
        prefs(context).edit().putString(KEY_URL, url).apply()
    }

    fun lastCheck(context: Context): Long =
        prefs(context).getLong(KEY_LAST_CHECK, 0L)

    fun setLastCheck(context: Context, timestamp: Long) {
        prefs(context).edit().putLong(KEY_LAST_CHECK, timestamp).apply()
    }

    private fun prefs(context: Context) =
        context.getSharedPreferences(FILE, Context.MODE_PRIVATE)
}
