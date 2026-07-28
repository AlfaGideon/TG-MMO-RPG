"""Страница: сводка."""
from engine import auction, items
from webapp.html import esc

TITLE = "📊 Сводка"
CRUMBS = [("Dashboard", "dash")]


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

    return f"""
<div class="card">
  <h2>🤖 Состояние бота</h2>
  <p class="muted">Бот: {status} · Аккаунт: <code>{esc(who)}</code> ·
     апдейтов: {bot.counters['updates']} · отправлено: {bot.counters['sent']} ·
     ошибок: {bot.counters['errors']}</p>
  <div style="margin-top:.7rem;display:flex;gap:.5rem;flex-wrap:wrap">
    <button class="btn primary" data-act="nav" data-arg="bot">⚙️ Управление ботом</button>
    <button class="btn" data-act="nav" data-arg="world">🗺 Карта мира</button>
  </div>
</div>

<div class="card"><h2>📈 Показатели</h2><div class="grid g4">{grid}</div></div>

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
