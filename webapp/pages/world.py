"""Страница: карта мира, сетка мира и редактор подземелий."""
from engine import data, world as W
from webapp.pages import dungeons as page_dungeons
from webapp.pages import world_forms as forms
from webapp.html import esc

TITLE = "🗺 Мир"
CRUMBS = [("Мир", "world")]

# Формы-модалки живут в world_forms.py; отсюда их забирают действия.
cell_form = forms.cell_form
grid_place_form = forms.grid_place_form
grid_edit_form = forms.grid_edit_form
loc_form = forms.loc_form


def render(ctx):
    tab = ctx.state.setdefault("world_tab", "map")

    # Sub-tab buttons
    tab_buttons = "".join(
        f"<button class='btn {'primary' if tab == t else ''}' data-act='world-tab' data-arg='{t}'>{label}</button> "
        for t, label in [("map", "🗺 Локации"), ("grid", "🌐 Сетка мира (10x10)"), ("dungeons", "🗝 Подземелья & Порталы")]
    )

    content = ""
    if tab == "map":
        content = _render_map(ctx)
    elif tab == "grid":
        content = _render_grid(ctx)
    elif tab == "dungeons":
        content = page_dungeons.render(ctx)

    return f"""
<div class="card">
  <h2>🗺 Разделы мира</h2>
  <div style="margin-bottom:.5rem;display:flex;gap:.4rem;flex-wrap:wrap">{tab_buttons}</div>
</div>
{content}
"""


def _render_map(ctx):
    li = ctx.state.get("loc", 0)
    if li >= len(data.LOCATIONS):
        li = 0
    tabs = "".join(
        f"<button class='btn {'primary' if i == li else ''}' data-act='world-loc' data-arg='{i}'>"
        f"{esc(l[0])}</button>" for i, l in enumerate(data.LOCATIONS))

    fog_player_id = ctx.state.get("fog_player", "")
    fog_player = ctx.store.players.get(int(fog_player_id)) if fog_player_id else None

    cells = ""
    for x in range(W.SIZE):
        for y in range(W.SIZE):
            c = ctx.store.world.get(f"{li}:{x}:{y}")
            if not c:
                continue
            color = data.TILE_COLORS.get(c.tile, "#333")
            mark = ""

            # Show players here
            player_here = []
            for p in ctx.store.players.values():
                if p.created_char and p.loc == li and p.x == x and p.y == y:
                    player_here.append(p.name[:2])

            if player_here:
                mark = f"<span style='font-size:0.6rem;font-weight:bold;color:#fff;background:var(--accent);padding:1px 2px;border-radius:3px;'>{'|'.join(player_here)}</span>"
            elif c.link:
                mark = "🚪"
            elif c.mob >= 0:
                mark = "👾"
            elif c.npc >= 0:
                mark = "💬"
            elif c.chest:
                mark = "📦"
            elif (x, y) == W.SPAWN and li == 0:
                mark = "⭐"

            in_fog = False
            if fog_player and fog_player.loc == li:
                if abs(x - fog_player.x) > 2 or abs(y - fog_player.y) > 2:
                    in_fog = True

            cell_style = f"background:{color};"
            if in_fog:
                cell_style += "opacity:0.25; filter:grayscale(80%);"

            cells += (f"<div class='c' style='{cell_style}' title='{esc(c.name)} [{x},{y}]' "
                      f"data-act='cell-edit' data-arg='{li}:{x}:{y}'>{mark}</div>")

    legend = "".join(f"<span><i class='sw' style='background:{v}'></i>{k}</span>"
                     for k, v in data.TILE_COLORS.items())
    mobs = sum(1 for c in ctx.store.world.values() if c.loc == li and c.mob >= 0)
    chests = sum(1 for c in ctx.store.world.values() if c.loc == li and c.chest)
    walls = sum(1 for c in ctx.store.world.values() if c.loc == li and not c.passable)

    player_options = "<option value=''>— Отключён —</option>" + "".join(
        f"<option value='{p.tg_id}' {'selected' if fog_player_id == str(p.tg_id) else ''}>{esc(p.name)} (ур.{p.level})</option>"
        for p in ctx.store.players.values() if p.created_char
    )

    brush_opts = "".join(f"<option value='{t}' >{t}</option>" for t in data.TILE_COLORS)
    brush_palette_html = """
    <div style='display:flex;gap:6px;flex-wrap:wrap'>
      <button class='btn sm' data-brush='wall'>🧱 Стена</button>
      <button class='btn sm' data-brush='grass'>🌿 Трава</button>
      <button class='btn sm' data-brush='forest'>🌲 Лес</button>
      <button class='btn sm' data-brush='water'>💧 Вода</button>
      <button class='btn sm' data-brush='road'>🛤 Дорога</button>
      <button class='btn sm' data-brush='village'>🏘 Деревня</button>
      <button class='btn sm' data-brush='cave'>🕳 Пещера</button>
      <button class='btn sm' data-brush='portal'>🌀 Портал</button>
    </div>
    <div style='display:flex;gap:6px;flex-wrap:wrap;margin-top:4px'>
      <button class='btn sm' data-brush='door'>🚪 Дверь (1 клетка-переход)</button>
      <button class='btn sm' data-brush='npc'>💬 NPC</button>
      <button class='btn sm' data-brush='chest'>📦 Сундук</button>
      <button class='btn sm' data-brush='clear'>🧹 Очист.</button>
    </div>
    """
    return f"""
<div class="card">
  <h2>🗺 Выберите локацию</h2>
  <div style="display:flex;gap:.4rem;flex-wrap:wrap;margin-bottom:1rem;">{tabs}</div>
  <div style="display:flex;align-items:center;gap:.5rem;margin-top:.5rem;flex-wrap:wrap">
    <span class="muted">Режим тумана войны (выберите игрока):</span>
    <select id="fogPlayerSelect" data-act="world-fog-select" style="max-width:200px;width:auto;">{player_options}</select>
  </div>
  <div style="margin-top:.7rem">
    <div class="muted" style="margin-bottom:.4rem">🖌 Современная кисть — ЛКМ/тяни рисует, ПКМ редактирует, дверь = 1 клетка-переход (а не стена), подуровни — стопка:</div>
    {brush_palette_html}
    <div style="margin-top:.4rem;display:flex;gap:4px;align-items:center;flex-wrap:wrap">
      <span class="muted">Выбрано: <b id="brushLabel">grass</b></span>
      <button class="btn sm primary" id="modePaint">🎨 Рисование</button>
      <button class="btn sm" id="modeInspect">👁️ Осмотр</button>
      <select id="paintBrush" style="display:none"><option value='grass'>grass</option>{brush_opts}</select>
    </div>
  </div>
</div>

<div class="card">
  <h2>{esc(data.LOCATIONS[li][0])}</h2>
  <p class="muted">{esc(data.LOCATIONS[li][1])} · тип: <span class="tag">{data.LOCATIONS[li][2]}</span>
     · мин. уровень {data.LOCATIONS[li][3]}</p>
  <p class="muted" style="margin-bottom:.7rem">👾 мобов: {mobs} · 📦 сундуков: {chests} · 🧱 стен: {walls}
     · ⭐ спавн [{W.SPAWN[0]},{W.SPAWN[1]}] · 🚪 переход в соседнюю локацию</p>
  <div class="mapgrid" id="locMapGrid">{cells}</div>
  <div class="legend">{legend}</div>
  <p class="muted" style="margin-top:.6rem">ЛКМ — закрасить выбранной кистью, ПКМ — редактировать клетку.</p>
</div>
<script>
(function(){{
  const grid = document.getElementById('locMapGrid');
  if (!grid) return;
  let painting = false;
  let currentMode = 'paint';
  // brush buttons
  document.querySelectorAll('[data-brush]').forEach(btn=>{
    btn.addEventListener('click', ()=>{
      const b = btn.dataset.brush;
      const sel = document.getElementById('paintBrush');
      if(sel) sel.value = b;
      document.getElementById('brushLabel').textContent = b;
      document.querySelectorAll('[data-brush]').forEach(x=>x.classList.remove('primary'));
      btn.classList.add('primary');
    });
  });
  document.getElementById('modePaint')?.addEventListener('click', ()=>{
    currentMode='paint';
    document.getElementById('modePaint').classList.add('primary');
    document.getElementById('modeInspect')?.classList.remove('primary');
    grid.style.cursor='crosshair';
  });
  document.getElementById('modeInspect')?.addEventListener('click', ()=>{
    currentMode='inspect';
    document.getElementById('modeInspect').classList.add('primary');
    document.getElementById('modePaint')?.classList.remove('primary');
    grid.style.cursor='pointer';
  });
  grid.addEventListener('mousedown', function(e){{
    const cell = e.target.closest('.c');
    if (!cell) return;
    if (e.button === 2) return;
    if (currentMode!=='paint') {{
      // inspect mode -> edit
      if (window.__app && window.__app.edit_cell) window.__app.edit_cell(cell.dataset.arg);
      return;
    }}
    painting = true;
    e.preventDefault();
    const brush = document.getElementById('paintBrush')?.value || 'grass';
    if(brush==='door'){{
      // door brush: open cell edit with door hint
      if (window.__app && window.__app.edit_cell) window.__app.edit_cell(cell.dataset.arg);
      return;
    }}
    window.__app && window.__app.paint_cell && window.__app.paint_cell(cell.dataset.arg, brush);
  }});
  grid.addEventListener('mouseover', function(e){{
    if (!painting) return;
    if (currentMode!=='paint') return;
    const cell = e.target.closest('.c');
    if (!cell) return;
    const brush = document.getElementById('paintBrush')?.value || 'grass';
    if(brush==='door') return;
    window.__app && window.__app.paint_cell && window.__app.paint_cell(cell.dataset.arg, brush);
  }});
  document.addEventListener('mouseup', function(){{ painting = false; }});
  grid.addEventListener('click', function(e){{
    if(currentMode!=='paint') return;
    // single click already handled in mousedown, but for safety
  }});
  grid.addEventListener('contextmenu', function(e){{
    e.preventDefault();
    const cell = e.target.closest('.c');
    if (cell && window.__app && window.__app.edit_cell) window.__app.edit_cell(cell.dataset.arg);
  }});
  // middle click pipette
  grid.addEventListener('auxclick', function(e){{
    if(e.button===1){{
      const cell = e.target.closest('.c');
      if(!cell) return;
      e.preventDefault();
      // read tile from background? use app state
      const arg = cell.dataset.arg;
      const storeCell = window.__app?.store?.world?.[arg];
      if(storeCell){{
        const tile = storeCell.tile;
        const sel = document.getElementById('paintBrush');
        if(sel) sel.value = tile;
        document.getElementById('brushLabel').textContent = tile;
      }}
    }}
  }});
}})();
</script>

{_render_loc_manager(ctx)}

<div class="card">
  <h2>🎲 Пересоздать мир</h2>
  <div class="hint warn">Мир будет сгенерирован заново по текущему списку локаций
     и сетке мира. Позиции игроков сбросятся на спавн, ручные правки клеток пропадут.</div>
  <div class="row">
    <div><label>Seed</label><input id="seedInput" value="{ctx.store.settings.get('seed',1337)}"></div>
    <div style="flex:0 0 auto"><button class="btn danger" data-act="world-regen">🎲 Перегенерировать</button></div>
  </div>
</div>
"""


def _render_loc_manager(ctx):
    """Список локаций мира: добавление и удаление + подуровни."""
    grid = ctx.store.settings.get("world_grid", {})
    floors_map = ctx.store.settings.get("location_floors", {})
    rows = ""
    for i, l in enumerate(data.LOCATIONS):
        wx, wy = grid.get(str(i), ["—", "—"])
        floors = floors_map.get(str(i), 1)
        linked = {c.link[0] for c in ctx.store.world.values()
                  if c.loc == i and c.link and c.link[0] != i}
        players = sum(1 for p in ctx.store.players.values()
                      if p.created_char and p.loc == i)
        floor_badge = f"🏢×{floors}" if floors>1 else "1 этаж"
        rows += (f"<tr><td>{esc(l[0])} <span style='font-size:0.7rem;color:var(--accent)'>{floor_badge}</span></td><td><span class='tag'>{l[2]}</span></td>"
                 f"<td>{l[3]}+</td><td>[{wx},{wy}]</td>"
                 f"<td>{'🔗 ' + str(len(linked)) if linked else '⚠️ нет'}</td>"
                 f"<td>{players or ''}</td>"
                 f"<td><button class='btn danger sm' data-act='world-loc-del' data-arg='{i}'>🗑</button></td></tr>")
    return f"""
<div class="card">
  <h2>🧭 Локации мира ({len(data.LOCATIONS)})</h2>
  <p class="muted">Новая локация сразу сшивается переходами с соседями по сетке
     мира. Удаление переиндексирует мир, сохраняя правки остальных локаций.</p>
  <table style="width:100%">
    <thead><tr><th>Название</th><th>Тип</th><th>Ур.</th><th>Сетка</th>
      <th>Швы</th><th>👥</th><th></th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <div style="margin-top:.8rem">
    <button class="btn primary" data-act="world-loc-new">➕ Добавить локацию</button>
  </div>
</div>
"""


def _render_grid(ctx):
    grid_settings = ctx.store.settings.setdefault("world_grid", dict(W.DEFAULT_GRID))
    floors_map = ctx.store.settings.get("location_floors", {})

    cells = ""
    for wy in range(10):
        for wx in range(10):
            loc_idx = None
            for idx, coords in grid_settings.items():
                if coords[0] == wx and coords[1] == wy:
                    loc_idx = int(idx)
                    break

            if loc_idx is not None and loc_idx < len(data.LOCATIONS):
                loc_name = data.LOCATIONS[loc_idx][0]
                floors = floors_map.get(str(loc_idx), 1)
                floor_badge = f"🏢×{floors}" if floors>1 else ""
                # визуализация подуровней как стопка: тень
                stack_style = "box-shadow:0 2px 0 #1a1a24,0 4px 0 var(--border),0 6px 0 #1a1a24;" if floors>1 else ""
                cells += (
                    f"<div class='c loc-cell' style='background:var(--accent); color:#fff; font-size:0.7rem; border-radius:4px; display:flex; flex-direction: column; align-items:center; justify-content:center; text-align:center; padding:2px; height:42px; cursor:pointer; {stack_style}' "
                    f"title='{esc(loc_name)} [{wx},{wy}] • этажей {floors} — подуровни видны как стопка' data-act='world-grid-edit' data-arg='{wx}:{wy}:{loc_idx}'>"
                    f"<b>L{loc_idx}</b><span style='font-size:0.5rem; overflow:hidden; text-overflow:ellipsis; width:100%; white-space:nowrap;'>{esc(loc_name[:8])}</span>"
                    f"<span style='font-size:0.45rem'>{floor_badge}</span>"
                    f"</div>"
                )
            else:
                cells += (
                    f"<div class='c' style='background:var(--bg-input); border:1px dashed var(--border); border-radius:4px; height:40px; display:flex; align-items:center; justify-content:center; cursor:pointer;' "
                    f"data-act='world-grid-place' data-arg='{wx}:{wy}'>"
                    f"<span style='color:var(--text-muted); font-size:0.6rem;'>+{wx},{wy}</span>"
                    f"</div>"
                )

    return f"""
<div class="card">
  <h2>🌐 Глобальная координатная сетка мира (10x10) — LIVE без F5</h2>
  <p class="muted" style="margin-bottom:0.6rem">
  Сетка боевая: соседние по ней локации сшиваются <b>одной дверью</b> в центре границы (а не стеной).
  Перетаскивай любую локацию на любую клетку — занятая = <b>обмен местами</b> без удаления.
  Пустая = клик для мгновенного создания на сетке. Подуровни (этажи) видны как стопка 🏢×N.
  </p>
  <div class="mapgrid" id="worldGrid" style="grid-template-columns: repeat(10, 1fr); max-width:520px; gap:6px;">{cells}</div>
  <div style="margin-top:.8rem;display:flex;gap:.5rem;flex-wrap:wrap">
    <button class="btn" data-act="world-relink">🔗 Пересшить (1 дверь)</button>
    <button class="btn" data-act="world-shuffle">🔀 Перемешать без удаления</button>
  </div>
  <p class="muted" style="margin-top:.6rem">💡 Нажми на пустую клетку — создаётся сразу на сетке. Двойной клик по локации — редактор. Drag&drop — обмен.</p>
</div>
<script>
(function(){{
  const grid = document.getElementById('worldGrid');
  if (!grid) return;
  let dragged = null;
  let draggedIdx = null;
  grid.querySelectorAll('.loc-cell').forEach(el => {{
    el.setAttribute('draggable', 'true');
    el.addEventListener('dragstart', function(e){{
      dragged = el.dataset.arg;
      draggedIdx = dragged.split(':')[2];
      el.style.opacity='0.4';
      e.dataTransfer.effectAllowed = 'move';
    }});
    el.addEventListener('dragend', function(){{ el.style.opacity=''; dragged=null; }})
  }});
  grid.addEventListener('dragover', function(e){{ e.preventDefault(); const cell=e.target.closest('.c'); if(cell) cell.style.outline='2px dashed var(--accent)'; }});
  grid.addEventListener('dragleave', function(e){{ const cell=e.target.closest('.c'); if(cell) cell.style.outline=''; }});
  grid.addEventListener('drop', function(e){{
    const cell = e.target.closest('.c');
    if (!cell || !dragged) return;
    e.preventDefault();
    cell.style.outline='';
    const parts = cell.dataset.arg.split(':');
    // drop на пустую: 2 части wx:wy, на занятую: 3 части wx:wy:locIdx
    let targetWx, targetWy;
    if(parts.length===2){{ targetWx=parts[0]; targetWy=parts[1]; }}
    else if(parts.length===3){{ targetWx=parts[0]; targetWy=parts[1]; }}
    else return;
    if(draggedIdx===null) return;
    // использовать world-grid-save который теперь умеет swap
    window.__app && window.__app.save_grid_loc && window.__app.save_grid_loc(draggedIdx, targetWx, targetWy);
    // fallback to old move
    if(window.__app && window.__app.move_world_loc) window.__app.move_world_loc(draggedIdx, targetWx, targetWy);
  }});
}})();
</script>
"""
