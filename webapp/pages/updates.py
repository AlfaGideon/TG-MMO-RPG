"""Страница: обновления и идеи игроков — паритет с серверной админкой.

Применены принципы из `jakubkrehel/skills`:
- better-ui: современные тени, скругления, микро-взаимодействия;
- better-accessibility: фокус-стейты, увеличенные области клика;
- better-typography: чёткая иерархия, межстрочный интервал 1.6;
- better-colors: контраст через var(--accent), var(--danger);
- better-layout: двухколоночная сетка, прогрессивное раскрытие;
- better-writing: понятные подписи, подсказывающие тексты.
"""
TITLE = "📢 Обновления и Идеи"
CRUMBS = [("Обновления и Идеи", "updates")]


def render(ctx):
    s = ctx.store.settings
    updates = list(s.get("updates", []) or [])
    suggestions = list(s.get("suggestions", []) or [])

    def sort_key(x):
        try:
            return int(x.get("created_at", "0"))
        except (ValueError, TypeError):
            return 0

    updates.sort(key=sort_key, reverse=True)
    suggestions.sort(key=sort_key, reverse=True)

    return f"""
<style>
  /* Применяем принципы better-ui и better-accessibility */
  .updates-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
    gap: 2rem;
    align-items: start;
  }}
  .card-modern {{
    background: var(--bg-card, #1e1e24);
    border: 1px solid var(--border, #2a2a30);
    border-radius: 16px;
    padding: 1.5rem;
    box-shadow: 0 4px 24px rgba(0,0,0,0.25), 0 1px 3px rgba(0,0,0,0.12);
    transition: box-shadow 0.2s ease, transform 0.15s ease;
  }}
  .card-modern:hover {{
    box-shadow: 0 8px 32px rgba(0,0,0,0.35), 0 2px 6px rgba(0,0,0,0.18);
    transform: translateY(-1px);
  }}
  .section-sub {{
    color: var(--text-muted, #888);
    font-size: 0.88rem;
    line-height: 1.5;
    margin-bottom: 1.25rem;
  }}
  .form-label {{
    font-weight: 600;
    font-size: 0.82rem;
    letter-spacing: 0.01em;
    color: var(--text, #e8e8ec);
    margin-bottom: 0.35rem;
    display: block;
  }}
  input, select, textarea {{
    border-radius: 10px;
    border: 1px solid var(--border, #2a2a30);
    background: var(--bg, #16161a);
    color: var(--text, #e8e8ec);
    padding: 0.65rem 0.9rem;
    font-size: 0.92rem;
    line-height: 1.5;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
  }}
  input:focus, select:focus, textarea:focus {{
    outline: none;
    border-color: var(--accent, #6aaeff);
    box-shadow: 0 0 0 3px rgba(106,174,255,0.15);
  }}
  .btn {{ border-radius: 10px; padding: 0.55rem 1.1rem; font-weight: 600; font-size: 0.88rem; }}
  .btn-sm {{ padding: 0.3rem 0.7rem; font-size: 0.78rem; }}
  .badge {{ border-radius: 999px; padding: 0.2rem 0.65rem; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.03em; text-transform: uppercase; }}
</style>

<div class="updates-grid">
  <!-- Левая колонка: обновления -->
  <section aria-label="Публикация и история обновлений">
    <article class="card-modern" aria-label="Форма публикации обновления">
      <h2 style="margin-top:0; font-size:1.15rem; letter-spacing:-0.01em;">📢 Выпустить обновление</h2>
      <p class="section-sub">Добавьте информацию о нововведениях или изменениях функций. Тип «Изменение» покажет было/стало.</p>
      <form data-act="publish-update" aria-label="Форма нового обновления">
        <div style="margin-bottom:1rem;">
          <label class="form-label" for="updTitle">Заголовок / Название функции</label>
          <input id="updTitle" name="title" type="text" required class="search-box" style="max-width:100%" placeholder="Например: VIP-система или Изменение урона" aria-required="true">
        </div>
        <div style="margin-bottom:1rem;">
          <label class="form-label" for="updType">Тип изменения</label>
          <select id="updType" name="change_type" class="search-box" style="max-width:100%"
            onchange="var g=document.getElementById('updWas'); g.style.display=this.value=='change'?'block':'none'; var l=document.getElementById('updBecameLabel'); l.textContent=this.value=='change'?'Как стало (became)':'Описание новинки';" aria-label="Тип изменения">
            <option value="new">⭐ Новинка</option>
            <option value="change">🔄 Изменение (Было → Стало)</option>
          </select>
        </div>
        <div id="updWas" style="margin-bottom:1rem; display:none;">
          <label class="form-label" for="updWasText">Как было (was)</label>
          <textarea id="updWasText" name="was_text" class="search-box" style="max-width:100%; height:80px; resize:vertical;" placeholder="Например: VIP-статус давал +20% золота..." aria-label="Как было"></textarea>
        </div>
        <div style="margin-bottom:1rem;">
          <label id="updBecameLabel" class="form-label" for="updBecame">Описание новинки</label>
          <textarea id="updBecame" name="became_text" required class="search-box" style="max-width:100%; height:100px; resize:vertical;" placeholder="Опишите новую функцию или результат изменения..." aria-required="true"></textarea>
        </div>
        <button type="submit" class="btn btn-primary" aria-label="Опубликовать обновление">🚀 Опубликовать</button>
      </form>
    </article>
    {_render_updates(updates)}
  </section>

  <!-- Правая колонка: идеи -->
  <section aria-label="Пожелания и идеи игроков">
    <article class="card-modern" aria-label="Предложения игроков">
      <h2 style="margin-top:0; font-size:1.15rem; letter-spacing:-0.01em;">💡 Пожелания и идеи игроков</h2>
      <p class="section-sub">Предложения приходят из бота. Вы можете взять в работу, принять или отклонить с комментарием.</p>
      {_render_suggestions(suggestions)}
    </article>
  </section>
</div>
"""


def _render_updates(updates):
    if not updates:
        return '<article class="card-modern" aria-label="История обновлений пуста"><h2 style="margin-top:0">📜 История обновлений</h2><p style="color:var(--text-muted); font-size:0.9rem;">Нет опубликованных обновлений.</p></article>'
    items = []
    for i, up in enumerate(updates):
        up_id = up.get("id", i)
        change_type = up.get("change_type", "new")
        title = up.get("title", "Без названия")
        created = up.get("created_at", "")
        was_text = up.get("was_text", "")
        became_text = up.get("became_text", "")
        if change_type == "change" and was_text:
            body = (
                '<div style="font-size:0.9rem; line-height:1.55; margin-top:0.5rem;">'
                '<div style="color:#ff5555; text-decoration:line-through; margin-bottom:0.25rem; font-weight:500;">'
                '<b>Было:</b> ' + (was_text or "—") + '</div>'
                '<div style="color:#55ff55; font-weight:500;">'
                '<b>Стало:</b> ' + (became_text or "—") + '</div>'
                '</div>')
        else:
            body = '<p style="font-size:0.92rem; line-height:1.55; margin:0.4rem 0 0; color:var(--text);">' + (became_text or "—") + '</p>'
        items.append(f"""
        <article class="card-modern" style="margin-top:1.25rem; position:relative;" aria-label="Обновление: {title}">
          <form action="#" data-act="delete-update" data-arg="{up_id}" style="position:absolute; top:1rem; right:1rem; z-index:2;">
            <input type="hidden" name="update_id" value="{up_id}">
            <button type="submit" class="btn btn-danger btn-sm" onclick="return confirm('Удалить эту запись?');" aria-label="Удалить обновление" title="Удалить">🗑</button>
          </form>
          <h3 style="font-size:1.05rem; margin-bottom:0.35rem; padding-right:2.5rem; letter-spacing:-0.01em; line-height:1.3;">
            <span aria-hidden="true">{"🔄" if change_type == "change" else "⭐"}</span>
            <span>{title}</span>
          </h3>
          <time datetime="{created}" style="font-size:0.75rem; color:var(--text-muted); display:block; margin-bottom:0.75rem;">{created}</time>
          {body}
        </article>
        """)
    return '<section aria-label="История обновлений">' + "".join(items) + '</section>'


def _render_suggestions(suggestions):
    if not suggestions:
        return '<p style="color:var(--text-muted); font-size:0.9rem;">Пожеланий от игроков пока не поступало.</p>'
    items = []
    for s in suggestions:
        s_id = s.get("id", s.get("created_at", 0))
        text = s.get("text", "")
        status = s.get("status", "pending")
        created = s.get("created_at", "")
        badge = {
            "pending": '<span class="badge" style="background:#e67e22; color:#fff;">Ожидает</span>',
            "taken_in_work": '<span class="badge" style="background:#3498db; color:#fff;">В работе</span>',
            "rejected": '<span class="badge" style="background:#95a5a6; color:#fff;">Отклонено</span>',
            "accepted_implemented": '<span class="badge" style="background:#2ecc71; color:#fff;">Реализовано</span>',
        }.get(status, '')
        buttons = []
        if status == "pending":
            buttons.append(f'<form data-act="suggest-action" data-arg="{s_id}:take_in_work" aria-label="Взять в работу"><input type="hidden" name="s_id" value="{s_id}"><input type="hidden" name="action" value="take_in_work"><button type="submit" class="btn btn-primary btn-sm" aria-label="Взять в работу">🛠️ Взять в работу</button></form>')
            buttons.append(f'<form data-act="suggest-action" data-arg="{s_id}:complete" aria-label="Реализовать"><input type="hidden" name="s_id" value="{s_id}"><input type="hidden" name="action" value="complete"><button type="submit" class="btn btn-sm" style="background:#2ecc71; color:#fff;" aria-label="Принять и реализовать">🎉 Реализовать</button></form>')
            buttons.append(f'<form data-act="suggest-action" data-arg="{s_id}:reject" aria-label="Отклонить"><input type="hidden" name="s_id" value="{s_id}"><input type="hidden" name="action" value="reject"><input type="hidden" name="comment" value="Отклонено"><button type="submit" class="btn btn-danger btn-sm" aria-label="Отклонить">❌ Отклонить</button></form>')
        elif status == "taken_in_work":
            buttons.append(f'<form data-act="suggest-action" data-arg="{s_id}:complete" aria-label="Принять и реализовать"><input type="hidden" name="s_id" value="{s_id}"><input type="hidden" name="action" value="complete"><button type="submit" class="btn btn-sm" style="background:#2ecc71; color:#fff;" aria-label="Принять и реализовать">🎉 Принять и Реализовать</button></form>')
            buttons.append(f'<form data-act="suggest-action" data-arg="{s_id}:reject" aria-label="Отклонить"><input type="hidden" name="s_id" value="{s_id}"><input type="hidden" name="action" value="reject"><input type="hidden" name="comment" value="Отклонено"><button type="submit" class="btn btn-danger btn-sm" aria-label="Отклонить">❌ Отменить / Отклонить</button></form>')
        elif status == "rejected":
            buttons.append(f'<form data-act="suggest-action" data-arg="{s_id}:take_in_work" aria-label="Вернуть в работу"><input type="hidden" name="s_id" value="{s_id}"><input type="hidden" name="action" value="take_in_work"><button type="submit" class="btn btn-primary btn-sm" aria-label="Вернуть в работу">🔄 Вернуть в работу</button></form>')
        btns_html = " ".join(f'<span style="display:inline-block;">{b}</span>' for b in buttons)
        items.append(f"""
        <article class="card-modern" style="margin-top:1rem;" aria-label="Предложение игрока">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:0.6rem; flex-wrap:wrap; gap:0.5rem;">
            <div>
              <span style="font-size:0.85rem; font-weight:700; color:var(--text);">👤 Игрок</span>
            </div>
            <div aria-label="Статус предложения">{badge}</div>
          </div>
          <blockquote style="font-size:0.95rem; line-height:1.6; margin:0 0 0.75rem; background:var(--bg, #16161a); padding:0.75rem 1rem; border-radius:10px; border-left:3px solid var(--accent, #6aaeff);">
            {text}
          </blockquote>
          <time datetime="{created}" style="font-size:0.72rem; color:var(--text-muted); display:block; margin-bottom:0.75rem;">Получено: {created}</time>
          <div style="display:flex; gap:0.5rem; flex-wrap:wrap; align-items:center;">
            {btns_html}
          </div>
        </article>
        """)
    return '<section aria-label="Список предложений">' + "".join(items) + '</section>'
