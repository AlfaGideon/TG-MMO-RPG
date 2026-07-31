"""Страница публикаций проекта и пожеланий игроков."""
from webapp.html import esc

TITLE = "📢 Обновления и идеи"
CRUMBS = [("Обновления и идеи", "updates")]

STATUS = {
    "pending": ("Ожидает", "warning"),
    "taken_in_work": ("В работе", "accent"),
    "rejected": ("Отклонено", "muted"),
    "accepted_implemented": ("Реализовано", "success"),
}


def _stamp(value):
    try:
        from js import Date
        return str(Date.new(int(value)).toLocaleString())
    except Exception:
        return "—"


def render(ctx):
    updates = sorted(ctx.store.settings.get("updates", []) or [],
                     key=lambda row: int(row.get("created_at") or 0), reverse=True)
    suggestions = sorted(ctx.store.settings.get("suggestions", []) or [],
                         key=lambda row: int(row.get("created_at") or 0), reverse=True)
    return f"""
<div class="updates-layout">
  <section>
    <div class="card updates-compose">
      <h2>📢 Выпустить обновление</h2>
      <p class="muted">Сообщи игрокам, что появилось или что изменилось.</p>
      <form data-act="publish-update" data-validate>
        <div><label for="updTitle">Заголовок</label>
          <input id="updTitle" type="text" required placeholder="Например: Новая система VIP"></div>
        <div><label for="updType">Тип</label>
          <select id="updType"><option value="new">⭐ Новинка</option>
            <option value="change">🔄 Изменение</option></select></div>
        <div id="updWasWrap" hidden><label for="updWasText">Как было</label>
          <textarea id="updWasText" rows="3" placeholder="Что меняется?"></textarea></div>
        <div><label id="updBecameLabel" for="updBecame">Описание новинки</label>
          <textarea id="updBecame" rows="4" required placeholder="Что получат игроки?"></textarea></div>
        <button class="btn primary" type="submit">🚀 Опубликовать</button>
      </form>
    </div>
    <div class="updates-list">{_updates(updates)}</div>
  </section>
  <section>
    <div class="card"><h2>💡 Идеи игроков</h2>
      <p class="muted">Выбери статус и, при необходимости, оставь понятный комментарий.</p>
      {_suggestions(suggestions)}
    </div>
  </section>
</div>
"""


def _updates(rows):
    if not rows:
        return "<div class='card empty-state'>Пока нет опубликованных обновлений.</div>"
    out = []
    for row in rows:
        uid = int(row.get("id") or 0)
        title, when = esc(row.get("title") or "Без названия"), _stamp(row.get("created_at"))
        was, became = esc(row.get("was_text") or ""), esc(row.get("became_text") or "—")
        if row.get("change_type") == "change":
            text = f"<div class='update-diff'><div class='was'>Было: {was or '—'}</div><div class='became'>Стало: {became}</div></div>"
            icon = "🔄"
        else:
            text, icon = f"<p>{became}</p>", "⭐"
        out.append(f"""
<article class="card update-card">
  <button class="btn danger btn-icon update-delete" data-act="delete-update" data-arg="{uid}"
    data-confirm="Удалить запись «{title}»? Это нельзя отменить." title="Удалить">🗑</button>
  <h2>{icon} {title}</h2><time class="muted">{esc(when)}</time>{text}
</article>""")
    return "".join(out)


def _suggestions(rows):
    if not rows:
        return "<div class='empty-state'>Пожеланий от игроков пока нет.</div>"
    out = []
    for row in rows:
        sid = int(row.get("id") or row.get("created_at") or 0)
        status = row.get("status", "pending")
        label, color = STATUS.get(status, STATUS["pending"])
        author = esc(row.get("author_name") or row.get("name") or "Игрок")
        tg_id = row.get("author_id") or row.get("tg_id")
        author += f" <span class='muted'>#{int(tg_id)}</span>" if str(tg_id or "").isdigit() else ""
        comment = esc(row.get("admin_comment") or "")
        controls = ""
        if status == "pending":
            controls = f"<button class='btn primary' data-act='suggest-action' data-arg='{sid}:take_in_work'>🛠 В работу</button> <button class='btn ok' data-act='suggest-action' data-arg='{sid}:complete'>✓ Реализовано</button> <button class='btn danger' data-act='suggest-action' data-arg='{sid}:reject'>Отклонить</button>"
        elif status == "taken_in_work":
            controls = f"<button class='btn ok' data-act='suggest-action' data-arg='{sid}:complete'>✓ Реализовано</button> <button class='btn danger' data-act='suggest-action' data-arg='{sid}:reject'>Отклонить</button>"
        else:
            controls = f"<button class='btn' data-act='suggest-action' data-arg='{sid}:take_in_work'>↻ Вернуть в работу</button>"
        out.append(f"""
<article class="suggestion-card">
  <div class="suggestion-head"><b>👤 {author}</b><span class="tag {color}">{label}</span></div>
  <blockquote>{esc(row.get('text') or '—')}</blockquote>
  <time class="muted">Получено: {esc(_stamp(row.get('created_at')))}</time>
  <label for="suggestComment{sid}">Комментарий администрации</label>
  <textarea id="suggestComment{sid}" rows="2" placeholder="Что ответить игроку?">{comment}</textarea>
  <div class="row-actions">{controls}</div>
</article>""")
    return "".join(out)
