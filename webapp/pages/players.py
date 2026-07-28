"""Страница: игроки и редактирование персонажа."""
from engine import data, permissions, rules
from webapp.html import esc

TITLE = "👥 Игроки"
CRUMBS = [("Игроки", "players")]


PER_PAGE = 15


SORTABLE = [
    ("name", "Имя"), ("level", "Ур."), ("gold", "Золото"),
    ("hp", "HP"), ("kills", "Убийств"),
]


def render(ctx):
    page = max(1, ctx.state.get("players_page", 1))
    sort = ctx.state.get("players_sort", "level")
    order = ctx.state.get("players_order", "desc")
    reverse = order == "desc"

    def key(p):
        val = getattr(p, sort, 0)
        if sort == "name":
            val = val.lower() if val else ""
        return val

    ps_all = sorted(ctx.store.players.values(), key=key, reverse=reverse)
    total = len(ps_all)
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = min(page, pages)
    ctx.state["players_page"] = page
    start = (page - 1) * PER_PAGE
    ps = ps_all[start:start + PER_PAGE]

    headers = "".join(
        f"<th><button class='sort-btn {'active' if sort == k else ''}' data-act='players-sort' data-arg='{k}'>{label} "
        f"{'▲' if sort == k and not reverse else '▼' if sort == k else '⇅'}</button></th>"
        for k, label in [("tg_id", "TG ID")] + SORTABLE + [("loc", "Позиция"), ("inv", "Предм.")]
    )
    rows = ""
    for p in ps:
        loc = data.LOCATIONS[p.loc][0] if p.loc < len(data.LOCATIONS) else "—"
        role_label = "—"
        if getattr(p, "is_web_admin", False):
            n = len(permissions.caps_of(p))
            role_label = (
                f"<span class='tag' style='color:var(--accent);border-color:var(--accent);"
                f"font-weight:bold'>{esc(permissions.rank_title(p.web_admin_role))}</span>"
                f" <span class='muted'>{n} прав</span>")
        rows += (
            f"<tr><td><input type='checkbox' class='row-check player-check' value='{p.tg_id}' onchange='updatePlayersMassCount()'></td>"
            f"<td><code>{p.tg_id}</code></td><td>{esc(p.name)}</td>"
            f"<td>{esc(p.cls) or '—'}</td><td>{p.level}</td>"
            f"<td>{p.hp}/{p.max_hp}</td><td>{p.gold} 🪙</td>"
            f"<td>{esc(loc)} [{p.x},{p.y}]</td><td>{len(p.inventory)}</td>"
            f"<td>{role_label}</td>"
            f"<td><button class='btn' data-act='player-edit' data-arg='{p.tg_id}'>✏️</button> "
            f"<button class='btn danger' data-act='player-del' data-arg='{p.tg_id}'>🗑</button></td></tr>")
    if not rows:
        rows = ("<tr><td colspan='11'><div class='empty-state'>"
                "<div class='empty-icon'>👥</div>"
                "<div>Пока никого. Запусти бота и напиши ему /start.</div>"
                "<button class='btn primary' data-act='nav' data-arg='bot'>🤖 Запустить бота</button>"
                "</div></td></tr>")

    pagination = ""
    if pages > 1:
        pagination = '<div class="pagination">'
        if page > 1:
            pagination += f"<button data-act='players-page' data-arg='{page - 1}'>←</button>"
        else:
            pagination += "<span>←</span>"
        for p in range(1, pages + 1):
            if p == page:
                pagination += f"<span class='current'>{p}</span>"
            elif p == 1 or p == pages or abs(p - page) <= 2:
                pagination += f"<button data-act='players-page' data-arg='{p}'>{p}</button>"
            elif abs(p - page) == 3:
                pagination += "<span>...</span>"
        if page < pages:
            pagination += f"<button data-act='players-page' data-arg='{page + 1}'>→</button>"
        else:
            pagination += "<span>→</span>"
        pagination += "</div>"

    return f"""
<div class="card">
  <h2>👥 Игроки <span class="muted">({start + 1}–{min(start + PER_PAGE, total)} из {total})</span></h2>
  <div class="mass-bar">
    <label style="display:flex;align-items:center;gap:.4rem;font-size:.85rem;color:var(--text-muted);cursor:pointer;">
      <input type="checkbox" class="row-check" data-act="players-select-all"> Все
    </label>
    <span class="mass-count" id="playersMassCount">Выбрано: 0</span>
    <button class="btn primary" data-act="players-mass-vip">👑 VIP 7 дней</button>
    <button class="btn danger" data-act="players-mass-del">🗑 Удалить</button>
  </div>
  <div class="scroll"><table>
    <tr><th style="width:40px"><input type="checkbox" class="row-check" data-act="players-select-all-header"></th>{headers}<th>Роль</th><th></th></tr>
    {rows}
  </table></div>
  {pagination}
  <div style="margin-top:.8rem">
    <button class="btn danger" data-act="players-wipe">🗑 Удалить всех игроков</button>
  </div>
</div>
"""


def edit_form(ctx, tg_id):
    p = ctx.store.players.get(int(tg_id))
    if not p:
        return "<p>Игрок не найден.</p>"
    f = lambda k, label, val: (
        f"<div><label>{label}</label><input id='pf_{k}' value='{val}'></div>")
    locs = "".join(f"<option value='{i}' {'selected' if i == p.loc else ''}>{esc(l[0])}</option>"
                   for i, l in enumerate(data.LOCATIONS))
    inv = "".join(f"<span class='chip'>{rules.item(i)['icon']} {esc(rules.item(i)['name'])}</span>"
                  for i in p.inventory) or "<span class='muted'>пусто</span>"
    give = "".join(f"<option value='{i}'>{esc(rules.item(i)['name'])}</option>"
                   for i in range(len(data.ITEMS)))
    
    return f"""
<h2>✏️ {esc(p.name)} <span class="muted">#{p.tg_id}</span></h2>
<div class="row" style="margin-top:.7rem">
  {f('name','Имя',esc(p.name))}{f('level','Уровень',p.level)}{f('gold','Золото',p.gold)}
</div>
<div class="row" style="margin-top:.5rem">
  {f('hp','HP',p.hp)}{f('max_hp','Max HP',p.max_hp)}{f('mp','MP',p.mp)}{f('max_mp','Max MP',p.max_mp)}
</div>
<div class="row" style="margin-top:.5rem">
  {f('strength','Сила',p.strength)}{f('agility','Ловкость',p.agility)}
  {f('intelligence','Интеллект',p.intelligence)}{f('endurance','Вынослив.',p.endurance)}
  {f('luck','Удача',p.luck)}
</div>
<div class="row" style="margin-top:.5rem">
  <div><label>Локация</label><select id='pf_loc'>{locs}</select></div>
  {f('x','X',p.x)}{f('y','Y',p.y)}
</div>
<h3>Инвентарь</h3><div>{inv}</div>
<div class="row" style="margin-top:.5rem">
  <div><label>Выдать предмет</label><select id='pf_give'>{give}</select></div>
  <div style="flex:0 0 auto"><button class="btn" data-act="player-give" data-arg="{p.tg_id}">🎁 Выдать</button></div>
</div>
<div style="margin-top:1rem;display:flex;gap:.5rem;flex-wrap:wrap">
  <button class="btn primary" data-act="player-save" data-arg="{p.tg_id}">💾 Сохранить</button>
  <button class="btn" data-act="player-heal" data-arg="{p.tg_id}">💊 Восстановить</button>
  <button class="btn" data-act="player-access" data-arg="{p.tg_id}">🔑 Права доступа</button>
  <button class="btn" data-act="modal-close">Отмена</button>
</div>
"""


def access_form(ctx, tg_id):
    """Выдача доступа: ранг-пресет + точечные галочки по функциям."""
    p = ctx.store.players.get(int(tg_id))
    if not p:
        return "<p>Игрок не найден.</p>"

    active = permissions.caps_of(p)
    ranks = "".join(
        f"<option value='{r}' {'selected' if p.web_admin_role == r else ''}>"
        f"{esc(permissions.rank_title(r))}</option>" for r in permissions.RANK_KEYS)

    groups = ""
    for group in permissions.CAP_GROUPS:
        boxes = ""
        for key, label, grp in permissions.CAPS:
            if grp != group:
                continue
            checked = "checked" if key in active else ""
            boxes += (
                f"<label class='capbox'><input type='checkbox' id='cap_{key}' {checked}>"
                f"<span>{esc(label)}</span></label>")
        groups += (f"<div class='capgroup'><div class='capgroup-title'>{esc(group)}</div>"
                   f"{boxes}</div>")

    if p.is_web_admin:
        pwd = esc(p.web_admin_password or "— будет создан при выдаче —")
        state = (f"<div class='hint'>Доступ выдан · ранг "
                 f"<b>{esc(permissions.rank_title(p.web_admin_role))}</b><br>"
                 f"Логин: <code>{p.tg_id}</code> · Пароль: <code>{pwd}</code></div>")
    else:
        state = ("<div class='hint warn'>Доступ пока не выдан. При выдаче игрок получит "
                 "в боте логин, пароль и кнопку «🛠 Админка» в меню.</div>")

    return f"""
<h2>🔑 Доступ: {esc(p.name)} <span class="muted">#{p.tg_id}</span></h2>
{state}
<div class="row" style="margin-top:.6rem">
  <div><label>Ранг (пресет прав)</label><select id="acc_rank">{ranks}</select></div>
  <div style="flex:0 0 auto"><label>&nbsp;</label>
    <button class="btn" data-act="access-preset" data-arg="{p.tg_id}">↻ Применить пресет</button></div>
  <div style="flex:0 0 auto"><label>&nbsp;</label>
    <button class="btn" data-act="access-newpass" data-arg="{p.tg_id}">🎲 Новый пароль</button></div>
</div>
<h3 style="margin-top:.8rem">Доступ к функциям</h3>
<p class="muted">Отметь только то, что игроку разрешено — как ранги в кланах.</p>
<div class="capgrid">{groups}</div>
<div style="margin-top:1rem;display:flex;gap:.5rem;flex-wrap:wrap">
  <button class="btn primary" data-act="access-save" data-arg="{p.tg_id}">💾 Выдать доступ</button>
  {"<button class='btn danger' data-act='access-revoke' data-arg='" + str(p.tg_id) + "'>🚫 Отозвать</button>" if p.is_web_admin else ""}
  <button class="btn" data-act="modal-close">Отмена</button>
</div>
"""
