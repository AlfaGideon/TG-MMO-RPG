"""Мировая сетка 10×10: раскладка локаций, drag&drop-обмен, пересшивка."""
from engine import data, world as W
from webapp.html import esc


def render(ctx):
    grid = ctx.store.settings.setdefault("world_grid", dict(W.DEFAULT_GRID))
    floors_map = ctx.store.settings.get("location_floors", {})

    cells = ""
    for wy in range(10):
        for wx in range(10):
            loc_idx = next((int(i) for i, xy in grid.items()
                            if xy[0] == wx and xy[1] == wy), None)
            if loc_idx is not None and loc_idx < len(data.LOCATIONS):
                cells += _busy(loc_idx, wx, wy, floors_map)
            else:
                cells += _free(wx, wy)

    return f"""
<div class="card">
  <h2>🌐 Глобальная координатная сетка мира (10x10) — LIVE без F5</h2>
  <p class="muted" style="margin-bottom:0.6rem">
  Соседние по сетке локации сшиваются <b>одной дверью</b> в центре границы.
  Перетащи локацию на любую клетку — занятая означает <b>обмен местами</b>.
  Пустая — клик для создания. Подуровни видны как стопка 🏢×N.
  </p>
  <div class="mapgrid" id="worldGrid" style="grid-template-columns: repeat(10, 1fr); max-width:520px; gap:6px;">{cells}</div>
  <div style="margin-top:.8rem;display:flex;gap:.5rem;flex-wrap:wrap">
    <button class="btn" data-act="world-relink">🔗 Пересшить (1 дверь)</button>
    <button class="btn" data-act="world-shuffle">🔀 Перемешать без удаления</button>
  </div>
</div>
{_script()}
"""


def _busy(loc_idx, wx, wy, floors_map):
    name = data.LOCATIONS[loc_idx][0]
    floors = floors_map.get(str(loc_idx), 1)
    badge = f"🏢×{floors}" if floors > 1 else ""
    stack = ("box-shadow:0 2px 0 #1a1a24,0 4px 0 var(--border),0 6px 0 #1a1a24;"
             if floors > 1 else "")
    return (
        f"<div class='c loc-cell' style='background:var(--accent); color:#fff; font-size:0.7rem;"
        f" border-radius:4px; display:flex; flex-direction: column; align-items:center;"
        f" justify-content:center; text-align:center; padding:2px; height:42px; cursor:pointer; {stack}' "
        f"title='{esc(name)} [{wx},{wy}] • этажей {floors}' "
        f"data-act='world-grid-edit' data-arg='{wx}:{wy}:{loc_idx}'>"
        f"<b>L{loc_idx}</b><span style='font-size:0.5rem; overflow:hidden; text-overflow:ellipsis;"
        f" width:100%; white-space:nowrap;'>{esc(name[:8])}</span>"
        f"<span style='font-size:0.45rem'>{badge}</span></div>")


def _free(wx, wy):
    return (
        f"<div class='c' style='background:var(--bg-input); border:1px dashed var(--border);"
        f" border-radius:4px; height:40px; display:flex; align-items:center;"
        f" justify-content:center; cursor:pointer;' "
        f"data-act='world-grid-place' data-arg='{wx}:{wy}'>"
        f"<span style='color:var(--text-muted); font-size:0.6rem;'>+{wx},{wy}</span></div>")


def _script():
    return """
<script>
(function(){
  const grid = document.getElementById('worldGrid');
  if (!grid || grid.dataset.wired) return;
  grid.dataset.wired = '1';
  let draggedIdx = null;
  grid.querySelectorAll('.loc-cell').forEach(el => {
    el.setAttribute('draggable', 'true');
    el.addEventListener('dragstart', function(e){
      draggedIdx = el.dataset.arg.split(':')[2];
      el.style.opacity = '0.4';
      e.dataTransfer.effectAllowed = 'move';
    });
    el.addEventListener('dragend', function(){ el.style.opacity = ''; });
  });
  grid.addEventListener('dragover', function(e){
    e.preventDefault();
    const cell = e.target.closest('.c');
    if (cell) cell.style.outline = '2px dashed var(--accent)';
  });
  grid.addEventListener('dragleave', function(e){
    const cell = e.target.closest('.c');
    if (cell) cell.style.outline = '';
  });
  grid.addEventListener('drop', function(e){
    const cell = e.target.closest('.c');
    if (!cell || draggedIdx === null) return;
    e.preventDefault();
    cell.style.outline = '';
    const parts = cell.dataset.arg.split(':');
    if (parts.length < 2) return;
    if (window.__app && window.__app.move_world_loc)
      window.__app.move_world_loc(draggedIdx, parts[0], parts[1]);
    draggedIdx = null;
  });
})();
</script>
"""
