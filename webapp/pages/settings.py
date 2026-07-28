"""Страница: настройки, экспорт/импорт, деплой."""
TITLE = "⚙️ Настройки"


def render(ctx):
    s = ctx.store.settings
    return f"""
<div class="card">
  <h2>🔄 Обновление проекта с GitHub</h2>
  <p class="muted">Нажми кнопку ниже, чтобы подтянуть последнюю версию интерфейса, функций бота и админки с GitHub.</p>
  <div style="margin-top:.7rem">
    <button class="btn ok" data-act="git-update">🔄 Обновить с GitHub</button>
  </div>
</div>

<div class="card">
  <h2>💾 Данные</h2>
  <p class="muted">Состояние (игроки + мир + токен) хранится в localStorage браузера.</p>
  <div style="margin-top:.7rem;display:flex;gap:.5rem;flex-wrap:wrap">
    <button class="btn" data-act="data-export">⬇️ Экспорт JSON</button>
    <button class="btn" data-act="data-import">⬆️ Импорт JSON</button>
    <button class="btn danger" data-act="data-reset">🗑 Полный сброс</button>
  </div>
  <textarea id="ioBox" rows="6" style="margin-top:.7rem" placeholder="Сюда попадёт экспорт / вставь JSON для импорта"></textarea>
</div>

<div class="card">
  <h2>🎛 Параметры игры</h2>
  <div class="row">
    <div><label>Seed мира</label><input id="setSeed" value="{s.get('seed', 1337)}"></div>
    <div><label>Стартовое золото</label><input id="setGold" value="{s.get('welcome_bonus', 50)}"></div>
    <div style="flex:0 0 auto"><button class="btn primary" data-act="settings-save">💾 Сохранить</button></div>
  </div>
</div>

<div class="card">
  <h2>🚀 Как это устроено</h2>
  <div class="hint">
    <b>index.html</b> — загрузчик: поднимает Python (Pyodide) в браузере и запускает
    <code>webapp/boot.py</code>. Ни строчки игровой логики на JS.<br><br>
    <b>engine/</b> — правила игры на чистом Python: <code>data.py</code> (контент),
    <code>world.py</code> (генерация мира), <code>rules.py</code> (формулы),
    <code>combat.py</code> (бой), <code>game.py</code> (роутер действий),
    <code>storage.py</code> (состояние).<br><br>
    <b>webapp/</b> — админка: <code>telegram.py</code> (long polling к Bot API),
    <code>pages/*.py</code> (страницы), <code>dom.py</code> (обёртка над DOM).<br><br>
    Тот же <code>engine/</code> можно подключить к серверному боту на aiogram —
    логика не изменится.
  </div>
  <p class="muted">Бот опрашивает Telegram, пока вкладка открыта. Закрыл вкладку — бот замолчал.
     Для 24/7 нужен серверный запуск (<code>launch.py</code>).</p>
</div>
"""
