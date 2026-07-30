"""Подземелья и порталы: список шаблонов, карта порталов, карточка.

Отдельный модуль, чтобы страница мира оставалась компактной.
"""
from engine import data, dungeon as D, storage, world as W
from webapp.html import esc


def render(ctx):
    dungeons = ctx.store.settings.setdefault(
        "dungeon_templates", storage.default_dungeons())


    rows = ""
    for dg in dungeons:
        portal = dg.get("portal_cell")
        opened_at = dg.get("opened_at", 0)
        if portal:
            li, x, y = map(int, portal.split(":"))
            # live timer 2 часа = 7200 сек
            status = f"<b style='color:var(--success)'>Активен: {esc(data.LOCATIONS[li][0])} [{x},{y}]</b><br><span class='badge live-timer' data-opened='{opened_at}'>⏳ загрузка...</span>"
            action_btn = f"<button class='btn danger' data-act='dungeon-close' data-arg='{dg['id']}'>❌ Закрыть портал</button>"
        else:
            status = "<span class='muted'>Закрыт</span>"
            action_btn = f"<button class='btn primary' data-act='dungeon-open' data-arg='{dg['id']}'>🚪 Открыть портал</button>"
            
        rows += f"""
        <tr>
          <td><b>{esc(dg['name'])}</b></td>
          <td class="muted">{esc(dg['desc'])}</td>
          <td>{dg['min_level']}</td>
          <td>{dg['grid_size']}x{dg['grid_size']}</td>
          <td>{status}</td>
          <td>
            <div style="display:flex;gap:.3rem;">
              {action_btn}
              <button class='btn danger' data-act='dungeon-delete' data-arg='{dg['id']}'>🗑</button>
            </div>
          </td>
        </tr>
        """
        
    if not rows:
        rows = "<tr><td colspan='6' class='muted'>Подземелий пока нет. Создайте новое ниже.</td></tr>"

    return f"""
<div class="card">
  <h2>🗝 Шаблоны подземелий & Порталы — LIVE таймеры</h2>
  <p class="muted" style="margin-bottom:1rem">Портал живёт 2 часа — таймер обновляется без перезагрузки. Открывайте порталы — игроки получат уведомление.</p>
  <div class="scroll"><table>
    <tr><th>Название</th><th>Описание</th><th>Мин. ур</th><th>Размер</th><th>Статус (live)</th><th>Действия</th></tr>
    {rows}
  </table></div>
</div>
<script>
(function(){{
  function fmt(s){{ if(s<=0) return '⏰ Закрыт'; const h=Math.floor(s/3600), m=Math.floor((s%3600)/60), sec=s%60; return `${{h}}ч ${{m}}м ${{sec}}с`; }}
  function tick(){{
    document.querySelectorAll('.live-timer[data-opened]').forEach(el=>{{
      const opened = parseFloat(el.dataset.opened||0);
      if(!opened){{ el.textContent='—'; return; }}
      const left = 7200 - Math.floor(Date.now()/1000 - opened);
      el.textContent = '⏳ '+fmt(left);
      if(left<=0){{ el.textContent='🚫 Авто-закрыт'; }}
    }});
    setTimeout(tick,1000);
  }}
  tick();
  }})();
</script>
</div>

{_runs(ctx, dungeons)}

{_portal_map(ctx, dungeons)}

<div class="card">
  <h2>🆕 Создать шаблон подземелья</h2>
  <div class="row" style="margin-top:.5rem">
    <div><label>Название</label><input id="dg_name" placeholder="Например: Древняя Шахта"></div>
    <div><label>Мин. уровень</label><input id="dg_level" type="number" value="1"></div>
    <div><label>Размер сетки</label><input id="dg_size" type="number" value="10"></div>
  </div>
  <div style="margin-top:.5rem">
    <label>Описание</label>
    <input id="dg_desc" placeholder="Краткое описание для игроков">
  </div>
  <div style="margin-top:1rem">
    <button class="btn primary" data-act="dungeon-create">➕ Создать шаблон</button>
  </div>
</div>
"""


def _runs(ctx, dungeons):
    """Кто сейчас внутри: раньше портал был декорацией, теперь в нём живут."""
    names = {int(d["id"]): d["name"] for d in dungeons}
    rows = ""
    inside = 0
    for p in ctx.store.players.values():
        run = D.run_of(p)
        if not run:
            continue
        inside += 1
        tpl = names.get(int(run.get("tpl", -1)), "?")
        seen = len(run.get("seen") or [])
        rows += (f"<tr><td>{esc(p.name)} <span class='muted'>ур. {p.level}</span></td>"
                 f"<td>{esc(tpl)}</td><td>этаж {run.get('floor', 1)}</td>"
                 f"<td>[{run.get('x', 0)},{run.get('y', 0)}]</td>"
                 f"<td>{seen} кл. · ☠️ {len(run.get('cleared') or [])}"
                 f" · 📦 {len(run.get('looted') or [])}</td></tr>")
    body = (f"<div class='scroll'><table><thead><tr><th>Герой</th>"
            f"<th>Подземелье</th><th>Этаж</th><th>Где</th><th>Прогресс</th>"
            f"</tr></thead><tbody>{rows}</tbody></table></div>") if rows else (
        "<p class='muted'>Внутри никого. Откройте портал — и герои полезут.</p>")
    return f"""
<div class="card">
  <h2>🕳 Сейчас в подземельях ({inside})</h2>
  <div class="hint">Портал теперь действительно ведёт внутрь: игрок входит
     с клетки, бродит по этажам, дерётся и вскрывает сундуки. Сетка не
     хранится, а восстанавливается из сида забега — сохранение не пухнет.
     Гибель внутри выбрасывает наружу.</div>
  {body}
</div>
"""


def _portal_map(ctx, dungeons):
    """Карта локации с отметками всех открытых порталов подземелий."""
    li = ctx.state.get("portal_loc", 0)
    by_cell = {d["portal_cell"]: d for d in dungeons if d.get("portal_cell")}

    tabs = ""
    for i, loc in enumerate(data.LOCATIONS):
        count = sum(1 for k in by_cell if k.startswith(f"{i}:"))
        badge = f" <b>({count}🌀)</b>" if count else ""
        tabs += (f"<button class='btn {'primary' if i == li else ''}' "
                 f"data-act='portal-loc' data-arg='{i}'>{esc(loc[0])}{badge}</button> ")

    cells = ""
    for x in range(W.SIZE):
        for y in range(W.SIZE):
            key = f"{li}:{x}:{y}"
            c = ctx.store.world.get(key)
            if not c:
                continue
            dg = by_cell.get(key)
            color = data.TILE_COLORS.get(c.tile, "#333")
            if dg:
                dg_name = esc(dg["name"])
                dg_id = dg["id"]
                cells += (
                    f"<div class='c portal-cell' title='🌀 {dg_name} — {esc(c.name)} [{x},{y}]' "
                    f"data-act='dungeon-focus' data-arg='{dg_id}'>🌀</div>")
            else:
                mark = "🚪" if c.link else ("⬛" if not c.passable else "")
                cells += (f"<div class='c' style='background:{color};opacity:.55' "
                          f"title='{esc(c.name)} [{x},{y}]'>{mark}</div>")

    open_rows = ""
    for dg in dungeons:
        key = dg.get("portal_cell")
        if not key:
            continue
        cl, cx, cy = map(int, key.split(":"))
        open_rows += (f"<tr><td>🌀 <b>{esc(dg['name'])}</b></td>"
                      f"<td>{esc(data.LOCATIONS[cl][0])}</td><td><code>[{cx},{cy}]</code></td>"
                      f"<td>ур. {dg['min_level']}+</td>"
                      f"<td><button class='btn' data-act='portal-loc' data-arg='{cl}'>"
                      f"👁 Показать</button></td></tr>")
    if not open_rows:
        open_rows = "<tr><td colspan='5' class='muted'>Открытых порталов нет.</td></tr>"

    return f"""
<div class="card">
  <h2>🗺 Карта порталов</h2>
  <p class="muted">Где сейчас открыты входы в подземелья. Клик по 🌀 — открыть шаблон.</p>
  <div style="display:flex;gap:.4rem;flex-wrap:wrap;margin:.6rem 0">{tabs}</div>
  <div class="mapgrid">{cells}</div>
  <div class="legend">
    <span>🌀 портал</span><span>🚪 переход</span><span>⬛ стена</span>
  </div>
</div>

<div class="card">
  <h2>📍 Активные порталы</h2>
  <div class="scroll"><table>
    <tr><th>Подземелье</th><th>Локация</th><th>Клетка</th><th>Уровень</th><th></th></tr>
    {open_rows}
  </table></div>
</div>
"""


def dungeon_form(ctx, dg):
    """Карточка подземелья: где портал, чем закрыть/переоткрыть."""
    key = dg.get("portal_cell")
    if key:
        cl, cx, cy = map(int, key.split(":"))
        cell = ctx.store.world.get(key)
        where = (f"<div class='hint'>🌀 Портал открыт: <b>{esc(data.LOCATIONS[cl][0])}</b> "
                 f"[{cx},{cy}]<br><span class='muted'>{esc(cell.name if cell else '')}</span></div>")
        buttons = (f"<button class='btn danger' data-act='dungeon-close' "
                   f"data-arg='{dg['id']}'>❌ Закрыть портал</button>")
    else:
        where = "<div class='hint warn'>Портал закрыт — игроки не могут войти.</div>"
        buttons = (f"<button class='btn primary' data-act='dungeon-open' "
                   f"data-arg='{dg['id']}'>🚪 Открыть портал</button>")

    return f"""
<h2>🗝 {esc(dg['name'])}</h2>
<p class="muted">{esc(dg['desc'])}</p>
{where}
<div class="row" style="margin-top:.6rem">
  <div><label>Мин. уровень</label><input value="{dg['min_level']}" disabled></div>
  <div><label>Размер</label><input value="{dg['grid_size']}x{dg['grid_size']}" disabled></div>
</div>
<div style="margin-top:1rem;display:flex;gap:.5rem;flex-wrap:wrap">
  {buttons}
  <button class="btn danger" data-act="dungeon-delete" data-arg="{dg['id']}">🗑 Удалить</button>
  <button class="btn" data-act="modal-close">Закрыть</button>
</div>
"""


