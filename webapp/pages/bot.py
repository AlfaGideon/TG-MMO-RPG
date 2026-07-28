"""Страница: запуск бота, транспорт и лог."""
from webapp.html import esc
from webapp.transport import PRESETS

TITLE = "🤖 Бот"
CRUMBS = [("Бот", "bot")]

MODE_LABELS = {
    "direct": "Напрямую (без прокси)",
    "corsproxy": "corsproxy.io",
    "allorigins": "allorigins.win",
    "codetabs": "codetabs.com",
    "custom": "Свой адрес…",
}


def _transport_block(ctx):
    mode = ctx.store.settings.get("proxy_mode", "direct")
    url = ctx.store.settings.get("proxy_url", "")
    opts = "".join(
        f"<option value='{k}'{' selected' if k == mode else ''}>{esc(v)}</option>"
        for k, v in MODE_LABELS.items())
    return f"""
<div class="card">
  <h2>🔀 Транспорт до Telegram</h2>
  <div class="hint warn">С осени 2025 Telegram отклоняет запросы с браузерным
    User-Agent. Если «Напрямую» не работает — выбери прокси-релей и проверь токен снова.</div>
  <div class="row">
    <div><label>Режим</label><select id="proxyMode">{opts}</select></div>
    <div style="flex:2"><label>Свой прокси (префикс URL)</label>
      <input id="proxyUrl" value="{esc(url)}" placeholder="https://мой-релей/?url="></div>
    <div style="flex:0 0 auto"><button class="btn primary" data-act="proxy-save">💾 Применить</button></div>
  </div>
  <p class="muted" style="margin-top:.4rem">Текущий режим: <code>{esc(MODE_LABELS.get(mode, mode))}</code>
     · префикс: <code>{esc(PRESETS.get(mode, url) or '—')}</code></p>
</div>
"""


def render(ctx):
    token = ctx.store.settings.get("token", "")
    masked = (token[:10] + "…" + token[-5:]) if len(token) > 18 else ""
    on = ctx.bot.running
    who = f"@{ctx.bot.me['username']}" if ctx.bot.me else "—"

    log_html = "".join(
        f'<div><span class="t">{esc(t)}</span> <span class="{lvl}">{esc(msg)}</span></div>'
        for t, lvl, msg in reversed(ctx.log_lines[-200:])
    ) or '<div class="muted">Лог пуст.</div>'

    return f"""
<div class="card">
  <h2>🔑 Токен и запуск</h2>
  <div class="hint">Получи токен у <a href="https://t.me/BotFather" target="_blank">@BotFather</a>,
    вставь сюда и нажми «Запустить». Бот работает, пока открыта эта вкладка —
    опрос Telegram идёт прямо из браузера.</div>
  <div class="row">
    <div style="flex:3">
      <label>Telegram Bot Token</label>
      <input id="tokenInput" type="password" placeholder="123456789:AA…" value="{esc(token)}">
    </div>
    <div style="flex:0 0 auto">
      <button class="btn" data-act="token-eye">👁</button>
    </div>
  </div>
  <p class="muted" style="margin:.4rem 0 .8rem">
     Сохранённый токен: <code>{esc(masked) or '—'}</code> · Аккаунт: <code>{esc(who)}</code></p>
  <div style="display:flex;gap:.5rem;flex-wrap:wrap">
    <button class="btn ok" data-act="bot-start" {'disabled' if on else ''}>▶️ Запустить бота</button>
    <button class="btn danger" data-act="bot-stop" {'' if on else 'disabled'}>⏹ Остановить</button>
    <button class="btn" data-act="bot-check">🔎 Проверить токен</button>
    <button class="btn" data-act="token-forget">🗑 Забыть токен</button>
  </div>
</div>

{_transport_block(ctx)}

<div class="card">
  <h2>📣 Рассылка игрокам</h2>
  <textarea id="castText" rows="3" placeholder="Текст сообщения (HTML разрешён)"></textarea>
  <div style="margin-top:.5rem"><button class="btn primary" data-act="broadcast">Отправить всем</button></div>
</div>

<div class="card">
  <h2>📜 Лог <button class="btn" style="float:right" data-act="log-clear">Очистить</button></h2>
  <div class="log">{log_html}</div>
</div>
"""
