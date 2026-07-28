"""Страница: журнал действий администраторов (общий с ботом)."""
from engine import audit, permissions
from webapp.html import esc

TITLE = "📜 Действия"
CRUMBS = [("Действия", "audit")]

SRC_TABS = [("", "Все"), ("panel", "🖥 Панель"), ("bot", "🤖 Бот")]


def render(ctx):
    src = ctx.state.get("audit_src", "")
    who = ctx.state.get("audit_who", "")
    search = ctx.state.get("audit_search", "")
    date_from = ctx.state.get("audit_from", "")
    date_to = ctx.state.get("audit_to", "")
    items = audit.entries(ctx.store, source=src, who=int(who or 0),
                          search=search, date_from=date_from, date_to=date_to)

    tabs = "".join(
        f"<button class='btn {'primary' if src == key else ''}' "
        f"data-act='audit-src' data-arg='{key or 'all'}'>{esc(label)}</button> "
        for key, label in SRC_TABS)

    admins = [p for p in ctx.store.players.values()
              if getattr(p, "is_web_admin", False) or _acted(ctx.store, p.tg_id)]
    opts = "<option value='0'>— все админы —</option>" + "".join(
        f"<option value='{p.tg_id}'{' selected' if str(p.tg_id) == str(who) else ''}>"
        f"{esc(p.name)} #{p.tg_id}</option>" for p in admins)

    rows = ""
    for e in items:
        badge = audit.SOURCES.get(e.get("src"), "—")
        color = "var(--success)" if e.get("src") == "bot" else "var(--accent)"
        rows += (
            f"<tr><td class='muted' style='white-space:nowrap'>{esc(audit.stamp(e))}</td>"
            f"<td><span class='tag' style='color:{color};border-color:{color}'>{esc(badge)}</span></td>"
            f"<td><b>{esc(e.get('name', ''))}</b>"
            f"<div class='muted'>#{esc(e.get('who', 0))}</div></td>"
            f"<td>{esc(e.get('act', ''))}</td>"
            f"<td>{esc(e.get('target', '')) or '—'}</td>"
            f"<td class='muted'>{esc(e.get('detail', '')) or '—'}</td></tr>")
    if not rows:
        rows = ("<tr><td colspan='6' class='muted'>Записей пока нет. Любое действие "
                "админа — в панели или в боте — попадёт сюда.</td></tr>")

    total = audit.count(ctx.store)
    from_bot = audit.count(ctx.store, "bot")
    tiles = [("Всего записей", total), ("🤖 Из бота", from_bot),
             ("🖥 Из панели", total - from_bot), ("Показано", len(items))]
    grid = "".join(f"<div class='stat'><div class='v'>{v}</div>"
                   f"<div class='l'>{esc(k)}</div></div>" for k, v in tiles)

    return f"""
<div class="card">
  <h2>📜 Действия администраторов</h2>
  <p class="muted">Единый журнал: кнопки в веб-панели и кнопки в Telegram-боте
     пишут сюда одинаково. Так видно, кто и что сделал с миром и игроками.</p>
  <div class="grid g4" style="margin-top:.7rem">{grid}</div>
</div>

<div class="card">
  <h2>🔍 Фильтры</h2>
  <div style="display:flex;gap:.4rem;flex-wrap:wrap;margin-bottom:.6rem">{tabs}</div>
  <div class="row">
    <div><label>Администратор</label><select id="auditWho">{opts}</select></div>
    <div><label>Поиск</label><input id="auditSearch" value="{esc(search)}" placeholder="Действие, цель, детали..."></div>
    <div><label>С</label><input id="auditFrom" type="date" value="{esc(date_from)}"></div>
    <div><label>По</label><input id="auditTo" type="date" value="{esc(date_to)}"></div>
    <div style="flex:0 0 auto"><label>&nbsp;</label>
      <button class="btn" data-act="audit-filter">Применить</button></div>
    <div style="flex:0 0 auto"><label>&nbsp;</label>
      <button class="btn danger" data-act="audit-clear">🗑 Очистить журнал</button></div>
  </div>
</div>

<div class="card">
  <h2>🗂 Записи <span class="muted">({len(items)})</span></h2>
  <div class="scroll"><table>
    <tr><th>Когда</th><th>Откуда</th><th>Кто</th><th>Действие</th>
        <th>Цель</th><th>Подробности</th></tr>
    {rows}
  </table></div>
</div>

<div class="card">
  <h2>🤝 Синхронизация с ботом</h2>
  <div class="hint">Админ с доступом видит в боте кнопку <b>🛠 Админка</b> —
    там те же функции: сводка, игроки, выдача предметов, золото, уровни,
    порталы, рассылка и этот же журнал. Права те же самые
    ({len(permissions.CAP_KEYS)} штук), проверяются на каждое действие.</div>
  <p class="muted">Уведомления игрокам ставятся в общую очередь и уходят,
     как только бот запущен — из панели или из бота, неважно.</p>
</div>
"""


def _acted(store, tg_id):
    return any(int(e.get("who") or 0) == int(tg_id) for e in audit.entries(store))
