package com.alfagideon.shadowlands

import android.annotation.SuppressLint
import android.content.Intent
import android.net.Uri
import android.net.http.SslError
import android.os.Bundle
import android.view.KeyEvent
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.webkit.SslErrorHandler
import android.webkit.URLUtil
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.ActivityResultLauncher
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.button.MaterialButton

class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var swipe: SwipeRefreshLayout
    private lateinit var errorView: View
    private lateinit var updates: UpdateManager
    private var fileChooserCallback: ValueCallback<Array<Uri>>? = null
    private lateinit var fileChooserLauncher: ActivityResultLauncher<String>

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val toolbar = findViewById<MaterialToolbar>(R.id.toolbar)
        setSupportActionBar(toolbar)

        webView = findViewById(R.id.webView)
        swipe = findViewById(R.id.swipe)
        errorView = findViewById(R.id.errorBlock)
        findViewById<MaterialButton>(R.id.retryButton).setOnClickListener { loadHome() }

        // Загрузка файлов через <input type="file"> (например, картинки в админке).
        fileChooserLauncher =
            registerForActivityResult(ActivityResultContracts.GetContent()) { uri ->
                val callback = fileChooserCallback ?: return@registerForActivityResult
                callback.onReceiveValue(if (uri != null) arrayOf(uri) else null)
                fileChooserCallback = null
            }

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            allowFileAccess = true
            allowContentAccess = true
            mediaPlaybackRequiresUserGesture = false
            // Пользователь может указать свой http-сервер — разрешаем смешанный контент.
            mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            cacheMode = WebSettings.LOAD_DEFAULT
            loadWithOverviewMode = true
            useWideViewPort = true
            builtInZoomControls = true
            displayZoomControls = false
        }

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(
                view: WebView,
                request: WebResourceRequest
            ): Boolean {
                val uri = request.url ?: return false
                val scheme = uri.scheme ?: return false
                // http/https остаёмся внутри WebView, остальные схемы (tg:, mailto:, intent:) — наружу.
                if (scheme == "http" || scheme == "https") return false
                return openExternal(uri)
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                swipe.isRefreshing = false
                errorView.visibility = View.GONE
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?
            ) {
                if (request?.isForMainFrame == true) showError()
            }

            override fun onReceivedSslError(
                view: WebView?,
                handler: SslErrorHandler?,
                error: SslError?
            ) {
                // Допускаем самоподписанные сертификаты пользовательских серверов.
                handler?.proceed()
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
                webView: WebView?,
                callback: ValueCallback<Array<Uri>>?,
                params: FileChooserParams?
            ): Boolean {
                fileChooserCallback?.onReceiveValue(null)
                fileChooserCallback = callback
                return try {
                    fileChooserLauncher.launch("*/*")
                    true
                } catch (e: Exception) {
                    fileChooserCallback = null
                    false
                }
            }
        }

        swipe.setOnRefreshListener { webView.reload() }
        swipe.setOnChildScrollUpCallback { _, _ -> webView.scrollY > 0 }

        updates = UpdateManager(this)
        updates.register()

        loadHome()
        updates.autoCheck()
    }

    private fun loadHome() {
        errorView.visibility = View.GONE
        webView.loadUrl(Prefs.getUrl(this))
    }

    private fun showError() {
        swipe.isRefreshing = false
        errorView.visibility = View.VISIBLE
    }

    private fun openExternal(uri: Uri): Boolean {
        return try {
            startActivity(Intent(Intent.ACTION_VIEW, uri))
            true
        } catch (e: Exception) {
            Toast.makeText(
                this,
                getString(R.string.external_link_error, uri.scheme.orEmpty()),
                Toast.LENGTH_LONG
            ).show()
            true
        }
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.menu_main, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean = when (item.itemId) {
        R.id.action_back -> {
            webView.goBack()
            true
        }
        R.id.action_refresh -> {
            webView.reload()
            true
        }
        R.id.action_home -> {
            loadHome()
            true
        }
        R.id.action_check_update -> {
            updates.manualCheck()
            true
        }
        R.id.action_server_url -> {
            showUrlDialog()
            true
        }
        R.id.action_about -> {
            showAboutDialog()
            true
        }
        else -> super.onOptionsItemSelected(item)
    }

    private fun showUrlDialog() {
        val input = EditText(this).apply {
            setText(Prefs.getUrl(this@MainActivity))
            setSelection(text.length)
            hint = getString(R.string.server_url_hint)
        }
        AlertDialog.Builder(this)
            .setTitle(R.string.server_url_title)
            .setView(input)
            .setPositiveButton(R.string.save) { _, _ ->
                var url = input.text.toString().trim()
                if (url.isEmpty()) url = Prefs.DEFAULT_URL
                if (!URLUtil.isNetworkUrl(url)) {
                    Toast.makeText(this, R.string.server_url_invalid, Toast.LENGTH_LONG).show()
                    return@setPositiveButton
                }
                Prefs.setUrl(this, url)
                loadHome()
            }
            .setNegativeButton(R.string.cancel, null)
            .setNeutralButton(R.string.server_url_reset) { _, _ ->
                Prefs.setUrl(this, Prefs.DEFAULT_URL)
                loadHome()
            }
            .show()
    }

    private fun showAboutDialog() {
        val version = runCatching {
            @Suppress("DEPRECATION")
            packageManager.getPackageInfo(packageName, 0).versionName
        }.getOrNull() ?: "?"

        AlertDialog.Builder(this)
            .setTitle(R.string.app_name)
            .setMessage(getString(R.string.about_text, version))
            .setPositiveButton(R.string.check_update) { _, _ -> updates.manualCheck() }
            .setNeutralButton(R.string.about_github) { _, _ ->
                openExternal(Uri.parse("https://github.com/AlfaGideon/TG-MMO-RPG/releases"))
            }
            .setNegativeButton(R.string.close, null)
            .show()
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (keyCode == KeyEvent.KEYCODE_BACK && webView.canGoBack()) {
            webView.goBack()
            return true
        }
        return super.onKeyDown(keyCode, event)
    }

    override fun onResume() {
        super.onResume()
        updates.resumePendingInstall()
    }

    override fun onDestroy() {
        updates.unregister()
        webView.destroy()
        super.onDestroy()
    }
}
