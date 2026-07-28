"""Страница: сводка."""
from engine import auction, items
from webapp.html import esc

TITLE = "📊 Сводка"
CRUMBS = [("Dashboard", "dash")]


def _health(ctx):
    s = ctx.store.stats()
    empty_locs = [i for i, _ in enumerate(ctx.store.world) if not any(p.loc == i for p in ctx.store.players.values() if p.created_char)]
    expired_lots = [l for l in ctx.store.settings.get("auction", []) if l.get("status") == "expired"]
    return {
        "bot_running": ctx.bot.running,
        "empty_locs": empty_locs,
        "expired_lots": expired_lots,
        "players": s["players"],
    }


def render(ctx):
    s = ctx.store.stats()
    bot = ctx.bot
    eco = items.stats(ctx.store)
    market = auction.stats(ctx.store)
    tiles = [
        ("Игроков", s["players"]), ("Героев", s["heroes"]),
        ("Средний ур.", s["avg_level"]), ("Золота в мире", s["gold"]),
        ("Убито мобов", s["kills"]), ("Клеток мира", s["cells"]),
    ]
    grid = "".join(f'<div class="stat"><div class="v">{v}</div>'
                   f'<div class="l">{esc(k)}</div></div>' for k, v in tiles)

    eco_tiles = [
        ("🆔 Именных вещей", eco["total"]), ("🌟 Реликвий", eco["unique"]),
        ("⚡ Заточено", eco["upgraded"]), ("🔁 Торговались", eco["traded"]),
        ("🏛 Лотов сейчас", market["active"]), ("💸 Оборот", f"{market['turnover']} 🪙"),
    ]
    eco_grid = "".join(f'<div class="stat"><div class="v">{v}</div>'
                       f'<div class="l">{esc(k)}</div></div>' for k, v in eco_tiles)

    status = ("<b style='color:var(--success)'>работает</b>"
              if bot.running else "<b style='color:var(--danger)'>остановлен</b>")
    who = f"@{bot.me['username']}" if bot.me else "—"

    rows = ""
    top = sorted([p for p in ctx.store.players.values() if p.created_char],
                 key=lambda p: (p.level, p.exp), reverse=True)[:8]
    for p in top:
        rows += (f"<tr><td>{esc(p.name)}</td><td>{esc(p.cls)}</td><td>{p.level}</td>"
                 f"<td>{p.gold} 🪙</td><td>{p.kills}</td></tr>")
    if not rows:
        rows = "<tr><td colspan='5' class='muted'>Игроков пока нет — запусти бота и напиши ему /start</td></tr>"

    h = _health(ctx)
    health = "".join([
        f"<div class='health-item {'ok' if h['bot_running'] else 'warn'}'><span class='health-dot'></span>"
        f"<span>{'🤖 Бот работает' if h['bot_running'] else '🤖 Бот остановлен'}</span>"
        f"<button class='btn' data-act='nav' data-arg='bot'>Настройки</button></div>",
        f"<div class='health-item {'warn' if h['empty_locs'] else 'ok'}'><span class='health-dot'></span>"
        f"<span>{len(h['empty_locs'])} пустых локаций</span>" +
        ("<button class='btn' data-act='nav' data-arg='world'>Карта</button>" if h['empty_locs'] else "") + "</div>",
        f"<div class='health-item {'warn' if h['expired_lots'] else 'ok'}'><span class='health-dot'></span>"
        f"<span>{len(h['expired_lots'])} просроченных лота</span>" +
        ("<button class='btn' data-act='nav' data-arg='economy'>Аукцион</button>" if h['expired_lots'] else "") + "</div>",
        f"<div class='health-item ok'><span class='health-dot'></span>"
        f"<span>👥 Игроков: {h['players']}</span></div>",
    ])

    return f"""
<div class="card">
  <h2>🤖 Состояние бота</h2>
  <p class="muted">Бот: {status} · Аккаунт: <code>{esc(who)}</code> ·
     апдейтов: {bot.counters['updates']} · отправлено: {bot.counters['sent']} ·
     ошибок: {bot.counters['errors']}</p>
  <div class="quick-actions">
    <button class="btn" data-act="dash-heal">✨ Вылечить всех</button>
    <button class="btn" data-act="dash-broadcast">📣 Рассылка</button>
    <button class="btn primary" data-act="nav" data-arg="bot">⚙️ Управление ботом</button>
    <button class="btn" data-act="nav" data-arg="world">🗺 Карта мира</button>
  </div>
</div>

<div class="grid-2">
  <div class="card"><h2>🏥 Здоровье системы</h2><div class="health-list">{health}</div></div>
  <div class="card"><h2>📈 Показатели</h2><div class="grid g4">{grid}</div></div>
</div>

<div class="card">
  <h2>💰 Экономика</h2>
  <p class="muted">Уникальные вещи, аукцион и крафт. Подробности —
     в разделе «💰 Экономика».</p>
  <div class="grid g4" style="margin-top:.7rem">{eco_grid}</div>
  <div style="margin-top:.7rem">
    <button class="btn primary" data-act="nav" data-arg="economy">💰 Открыть экономику</button>
  </div>
</div>

<div class="card">
  <h2>🏆 Лучшие герои</h2>
  <div class="scroll"><table>
    <tr><th>Имя</th><th>Класс</th><th>Ур.</th><th>Золото</th><th>Убийств</th></tr>
    {rows}
  </table></div>
</div>
"""
