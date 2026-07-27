"""Страница: игроки и редактирование персонажа."""
from engine import data, rules
from webapp.html import esc

TITLE = "👥 Игроки"


def render(ctx):
    ps = sorted(ctx.store.players.values(), key=lambda p: -p.level)
    rows = ""
    for p in ps:
        loc = data.LOCATIONS[p.loc][0] if p.loc < len(data.LOCATIONS) else "—"
        rows += (
            f"<tr><td><code>{p.tg_id}</code></td><td>{esc(p.name)}</td>"
            f"<td>{esc(p.cls) or '—'}</td><td>{p.level}</td>"
            f"<td>{p.hp}/{p.max_hp}</td><td>{p.gold} 🪙</td>"
            f"<td>{esc(loc)} [{p.x},{p.y}]</td><td>{len(p.inventory)}</td>"
            f"<td><button class='btn' data-act='player-edit' data-arg='{p.tg_id}'>✏️</button> "
            f"<button class='btn danger' data-act='player-del' data-arg='{p.tg_id}'>🗑</button></td></tr>")
    if not rows:
        rows = "<tr><td colspan='9' class='muted'>Пока никого. Запусти бота и напиши /start.</td></tr>"

    return f"""
<div class="card">
  <h2>👥 Игроки <span class="muted">({len(ps)})</span></h2>
  <div class="scroll"><table>
    <tr><th>TG ID</th><th>Имя</th><th>Класс</th><th>Ур.</th><th>HP</th>
        <th>Золото</th><th>Позиция</th><th>Предм.</th><th></th></tr>
    {rows}
  </table></div>
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
  <button class="btn" data-act="modal-close">Отмена</button>
</div>
"""
