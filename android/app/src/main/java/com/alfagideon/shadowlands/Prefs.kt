package com.alfagideon.shadowlands

import android.content.Context

/** Хранилище настроек приложения: адрес веб-панели и время последней проверки обновлений. */
object Prefs {
    private const val FILE = "shadowlands_prefs"
    private const val KEY_URL = "server_url"
    private const val KEY_LAST_CHECK = "last_update_check"

    /**
     * Стартовый адрес зависит от издания (BuildConfig задан flavor'ом):
     * admin — корень панели, player — игровой раздел /player/.
     * Песочницы приложений раздельны (разные package → разные UID),
     * поэтому одинаковое имя файла префов не конфликтует.
     */
    val DEFAULT_URL: String = BuildConfig.DEFAULT_URL

    /** Путь точки входа издания: "" — корень (admin), "/player/" — игра (player). */
    val ENTRY_PATH: String = BuildConfig.ENTRY_PATH

    /**
     * Приводит адрес к точке входа издания:
     *  * player — любой сохранённый/введённый адрес дополняется /player/
     *    (игрок физически не может попасть в корень админ-панели);
     *  * admin  — остаётся как есть, лишь убирается хвостовой слэш не ломаем.
     */
    fun canonicalize(raw: String): String {
        val url = raw.trim().trimEnd('/')
        if (url.isEmpty()) return DEFAULT_URL
        val path = ENTRY_PATH.trimEnd('/')
        if (path.isNotEmpty() && !url.endsWith(path)) {
            return url + path
        }
        return url
    }

    fun getUrl(context: Context): String {
        val stored = prefs(context).getString(KEY_URL, null)
        // Миграция со старых сборок: игровое издание раньше по умолчанию
        // вело на GitHub Pages, где игры нет (404.html уводит в админку).
        // Переустановка APK сохраняет SharedPreferences, поэтому такой адрес
        // нужно молча выкинуть и вернуть новый дефолт с бэкенда.
        if (ENTRY_PATH.isNotEmpty() && stored != null && isPagesUrl(stored)) {
            prefs(context).edit().remove(KEY_URL).apply()
            return canonicalize(DEFAULT_URL)
        }
        return canonicalize(stored ?: DEFAULT_URL)
    }

    fun setUrl(context: Context, url: String) {
        prefs(context).edit().putString(KEY_URL, canonicalize(url)).apply()
    }

    private fun isPagesUrl(url: String): Boolean =
        url.contains("github.io", ignoreCase = true) ||
            url.contains("githubusercontent", ignoreCase = true)

    fun lastCheck(context: Context): Long =
        prefs(context).getLong(KEY_LAST_CHECK, 0L)

    fun setLastCheck(context: Context, timestamp: Long) {
        prefs(context).edit().putLong(KEY_LAST_CHECK, timestamp).apply()
    }

    private fun prefs(context: Context) =
        context.getSharedPreferences(FILE, Context.MODE_PRIVATE)
}
