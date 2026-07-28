"""Страница: настройки, экспорт/импорт, деплой."""
TITLE = "⚙️ Настройки"


def render(ctx):
    s = ctx.store.settings
    panel_url = s.get("panel_url", "")
    if panel_url:
        hint = (f"<div>Кнопка в боте ведёт на: "
                f"<code>{panel_url}/admin-login?uid=123456789</code></div>")
    else:
        hint = ("<div class='muted' style='color:var(--warning)'>⚠️ Адрес не задан — "
                "в боте кнопка «Открыть панель» не показывается.</div>")

    shim = """
<div class="card">
  <h2>🚪 Вход админов и 404 на GitHub Pages</h2>
  <div class="hint">Pages отдаёт только файлы — серверного маршрута
    <code>/admin-login</code> там нет, поэтому раньше была ошибка <b>404</b>.
    Теперь в репозитории лежит прокладка:
    <code>admin-login/index.html</code> (страница входа),
    <code>admin-login.html</code> (тот же вход рядом с корнем) и
    <code>404.html</code>, который ловит любой неизвестный путь и уводит
    на нужную страницу, сохраняя <code>?uid=</code>.</div>
  <p class="muted" style="line-height:1.7">
    Логин — Telegram ID, пароль игрок берёт в боте: <code>/admin</code> →
    <b>🔑 Логин и пароль</b>. После входа панель показывает только те разделы,
    на которые у него есть права, а в подвале меню появляется кнопка «Выйти».<br>
    <b>Важно:</b> состояние живёт в localStorage браузера, поэтому вход работает
    на том устройстве, где панель уже открывали. Для входа с любого устройства
    нужен серверный запуск (<code>launch.py</code>).
  </p>
</div>
"""

    return f"""
<div class="card">
  <h2>🔗 Адрес админ-панели</h2>
  <p class="muted">Ссылка, по которой панель открывается снаружи. Её бот подставляет
     в кнопку <b>🌐 Открыть панель</b> при выдаче доступа игроку.</p>
  <div class="row" style="margin-top:.6rem">
    <div style="flex:3"><label>Публичный адрес панели</label>
      <input id="panelUrl" value="{panel_url}" placeholder="https://my-game.onrender.com"></div>
    <div style="flex:0 0 auto"><label>&nbsp;</label>
      <button class="btn primary" data-act="panel-url-save">💾 Сохранить</button></div>
  </div>
  <div class="muted" style="margin-top:.5rem;line-height:1.7">
    {hint}
    <div>Схема <code>https://</code> добавится сама. <b>localhost не подойдёт</b> —
       Telegram требует публичный HTTPS-адрес.</div>
  </div>
</div>

{shim}

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
