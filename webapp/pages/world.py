"""Страница: карта мира, сетка мира и редактор подземелий."""
from engine import data, world as W
from webapp.pages import dungeons as page_dungeons
from webapp.html import esc

TITLE = "🗺 Мир"
CRUMBS = [("Мир", "world")]


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

    brush_opts = "".join(f"<option value='{t}' {'selected' if t == 'grass' else ''}>{t}</option>" for t in data.TILE_COLORS)
    return f"""
<div class="card">
  <h2>🗺 Выберите локацию</h2>
  <div style="display:flex;gap:.4rem;flex-wrap:wrap;margin-bottom:1rem;">{tabs}</div>
  <div style="display:flex;align-items:center;gap:.5rem;margin-top:.5rem;flex-wrap:wrap">
    <span class="muted">Режим тумана войны (выберите игрока):</span>
    <select id="fogPlayerSelect" data-act="world-fog-select" style="max-width:200px;width:auto;">{player_options}</select>
  </div>
  <div style="display:flex;align-items:center;gap:.5rem;margin-top:.5rem;flex-wrap:wrap">
    <span class="muted">Кисть для рисования:</span>
    <select id="paintBrush" style="max-width:150px;width:auto;">{brush_opts}</select>
    <span class="muted">Кликай по клеткам, чтобы закрасить. Для редактирования — клик правой кнопкой.</span>
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
  grid.addEventListener('mousedown', function(e){{
    const cell = e.target.closest('.c');
    if (!cell) return;
    if (e.button === 2) return; // right click -> edit via data-act
    painting = true;
    e.preventDefault();
    const brush = document.getElementById('paintBrush')?.value || 'grass';
    window.__app && window.__app.paint_cell && window.__app.paint_cell(cell.dataset.arg, brush);
  }});
  grid.addEventListener('mouseover', function(e){{
    if (!painting) return;
    const cell = e.target.closest('.c');
    if (!cell) return;
    const brush = document.getElementById('paintBrush')?.value || 'grass';
    window.__app && window.__app.paint_cell && window.__app.paint_cell(cell.dataset.arg, brush);
  }});
  document.addEventListener('mouseup', function(){{ painting = false; }});
  grid.addEventListener('contextmenu', function(e){{
    e.preventDefault();
    const cell = e.target.closest('.c');
    if (cell && window.__app && window.__app.edit_cell) window.__app.edit_cell(cell.dataset.arg);
  }});
}})();
</script>

<div class="card">
  <h2>🎲 Пересоздать мир</h2>
  <div class="hint warn">Мир будет сгенерирован заново. Позиции игроков сбросятся на спавн.</div>
  <div class="row">
    <div><label>Seed</label><input id="seedInput" value="{ctx.store.settings.get('seed',1337)}"></div>
    <div style="flex:0 0 auto"><button class="btn danger" data-act="world-regen">🎲 Перегенерировать</button></div>
  </div>
</div>
"""


def _render_grid(ctx):
    grid_settings = ctx.store.settings.setdefault("world_grid", {
        "0": [2, 2], "1": [2, 3], "2": [3, 3], "3": [4, 3], "4": [4, 4]
    })
    
    cells = ""
    for wy in range(10):
        for wx in range(10):
            loc_idx = None
            for idx, coords in grid_settings.items():
                if coords[0] == wx and coords[1] == wy:
                    loc_idx = int(idx)
                    break
            
            if loc_idx is not None:
                loc_name = data.LOCATIONS[loc_idx][0]
                cells += (
                    f"<div class='c loc-cell' style='background:var(--accent); color:#fff; font-size:0.7rem; border-radius:4px; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; padding:2px; height:40px; cursor:pointer;' "
                    f"title='{esc(loc_name)} [{wx},{wy}]' data-act='world-grid-edit' data-arg='{wx}:{wy}:{loc_idx}'>"
                    f"<b>L{loc_idx}</b><span style='font-size:0.5rem; overflow:hidden; text-overflow:ellipsis; width:100%; white-space:nowrap;'>{esc(loc_name[:8])}</span>"
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
  <h2>🌐 Глобальная координатная сетка мира (10x10)</h2>
  <p class="muted" style="margin-bottom:1rem">Размещайте локации на глобальной карте. Перетаскивайте размещённые локации на пустые клетки.</p>
  <div class="mapgrid" id="worldGrid" style="grid-template-columns: repeat(10, 1fr); max-width:480px; gap:4px;">{cells}</div>
</div>
<script>
(function(){{
  const grid = document.getElementById('worldGrid');
  if (!grid) return;
  let dragged = null;
  grid.querySelectorAll('.loc-cell').forEach(el => {{
    el.setAttribute('draggable', 'true');
    el.addEventListener('dragstart', function(e){{
      dragged = el.dataset.arg;
      e.dataTransfer.effectAllowed = 'move';
    }});
  }});
  grid.addEventListener('dragover', function(e){{
    const cell = e.target.closest('.c');
    if (cell && !cell.classList.contains('loc-cell')) e.preventDefault();
  }});
  grid.addEventListener('drop', function(e){{
    const cell = e.target.closest('.c');
    if (!cell || cell.classList.contains('loc-cell') || !dragged) return;
    e.preventDefault();
    const parts = cell.dataset.arg.split(':');
    if (parts.length !== 2) return;
    const locIdx = dragged.split(':')[2];
    window.__app && window.__app.move_world_loc && window.__app.move_world_loc(locIdx, parts[0], parts[1]);
  }});
}})();
</script>
"""


def cell_form(ctx, key):
    c = ctx.store.world.get(key)
    if not c:
        return "<p>Клетка не найдена.</p>"
    tiles = "".join(f"<option {'selected' if t == c.tile else ''}>{t}</option>"
                    for t in data.TILE_COLORS)
    mobs = "<option value='-1'>— нет —</option>" + "".join(
        f"<option value='{i}' {'selected' if i == c.mob else ''}>{esc(m[0])} (ур.{m[2]})</option>"
        for i, m in enumerate(data.MOBS))
    npcs = "<option value='-1'>— нет —</option>" + "".join(
        f"<option value='{i}' {'selected' if i == c.npc else ''}>{esc(n[0])}</option>"
        for i, n in enumerate(data.NPCS))
    return f"""
<h2>🔧 Клетка [{c.x},{c.y}] · {esc(data.LOCATIONS[c.loc][0])}</h2>
<form data-validate data-autosave>
<div style="margin-top:.7rem"><label>Название</label><input id="cf_name" value="{esc(c.name)}" required></div>
<div style="margin-top:.5rem"><label>Описание</label><textarea id="cf_desc" rows="3">{esc(c.desc)}</textarea></div>
<div class="row" style="margin-top:.5rem">
  <div><label>Тайл</label><select id="cf_tile">{tiles}</select></div>
  <div><label>Проходима</label><select id="cf_pass">
     <option value="1" {'selected' if c.passable else ''}>да</option>
     <option value="0" {'selected' if not c.passable else ''}>нет</option></select></div>
  <div><label>Сундук</label><select id="cf_chest">
     <option value="1" {'selected' if c.chest else ''}>есть</option>
     <option value="0" {'selected' if not c.chest else ''}>нет</option></select></div>
</div>
<div class="row" style="margin-top:.5rem">
  <div><label>Моб</label><select id="cf_mob">{mobs}</select></div>
  <div><label>NPC</label><select id="cf_npc">{npcs}</select></div>
</div>
{"<p class='muted' style='margin-top:.5rem'>🚪 Клетка-переход в локацию " + esc(data.LOCATIONS[c.link[0]][0]) + "</p>" if c.link else ""}
<div style="margin-top:1rem;display:flex;gap:.5rem">
  <button class="btn primary" data-act="cell-save" data-arg="{key}">💾 Сохранить</button>
  <button class="btn" data-act="modal-close">Отмена</button>
</div>
</form>
"""


def grid_place_form(ctx, wx, wy):
    options = "".join(f"<option value='{i}'>{esc(l[0])}</option>"
                      for i, l in enumerate(data.LOCATIONS))
    return f"""
<h2>🌐 Разместить локацию на сетке [{wx}, {wy}]</h2>
<div style="margin-top:.7rem">
  <label>Выберите локацию для привязки к координатам</label>
  <select id="grid_loc_idx">{options}</select>
</div>
<div style="margin-top:1rem;display:flex;gap:.5rem">
  <button class="btn primary" data-act="world-grid-save" data-arg="{wx}:{wy}">💾 Сохранить</button>
  <button class="btn" data-act="modal-close">Отмена</button>
</div>
"""


def grid_edit_form(ctx, wx, wy, loc_idx):
    loc_name = data.LOCATIONS[int(loc_idx)][0]
    return f"""
<h2>🌐 Локация на сетке: {esc(loc_name)} [{wx}, {wy}]</h2>
<p class="muted">Вы можете убрать эту локацию с координатной сетки.</p>
<div style="margin-top:1.5rem;display:flex;gap:.5rem">
  <button class="btn danger" data-act="world-grid-remove" data-arg="{loc_idx}">🗑 Убрать с сетки</button>
  <button class="btn" data-act="modal-close">Отмена</button>
</div>
"""
