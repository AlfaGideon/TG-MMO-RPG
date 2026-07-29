"""Карта локации: кисть, слои и боковой редактор клетки.

Редактор клетки — колонка справа от карты (`.dock`), а не модалка на весь
экран: раньше окно перекрывало сетку, и в режиме рисования кисть теряла
клетки. Теперь рисование и правка клетки живут рядом и не мешают друг другу.
"""
from engine import cataclysm, data, world as W
from webapp.html import esc
from webapp.pages import world_forms as forms

BRUSHES_MAIN = [("wall", "🧱 Стена"), ("grass", "🌿 Трава"), ("forest", "🌲 Лес"),
                ("water", "💧 Вода"), ("road", "🛤 Дорога"),
                ("village", "🏘 Деревня"), ("cave", "🕳 Пещера")]
BRUSHES_EXTRA = [("door", "🚪 Дверь (переход)"), ("npc", "💬 NPC"),
                 ("chest", "📦 Сундук"), ("clear", "🧹 Очистить")]


def render(ctx):
    li = ctx.state.get("loc", 0)
    if li >= len(data.LOCATIONS):
        li = 0
        ctx.state["loc"] = 0

    tabs = "".join(
        f"<button class='btn {'primary' if i == li else ''}' data-act='world-loc' "
        f"data-arg='{i}'>{esc(l[0])}</button> " for i, l in enumerate(data.LOCATIONS))

    return f"""
{_toolbar(ctx, li, tabs)}
<div class="mapdock">
  {_map_card(ctx, li)}
  <div class="dock" id="cellDock">{forms.cell_form(ctx, ctx.state.get("cell_pick", ""))}</div>
</div>
{_script()}
{_loc_manager(ctx)}
{_regen_card(ctx)}
"""


def _toolbar(ctx, li, tabs):
    fog_id = ctx.state.get("fog_player", "")
    players = "<option value=''>— Отключён —</option>" + "".join(
        f"<option value='{p.tg_id}' {'selected' if fog_id == str(p.tg_id) else ''}>"
        f"{esc(p.name)} (ур.{p.level})</option>"
        for p in ctx.store.players.values() if p.created_char)

    brush = ctx.state.get("brush", "grass")
    row1 = "".join(
        f"<button class='btn sm {'primary' if b == brush else ''}' data-brush='{b}'>{lbl}</button>"
        for b, lbl in BRUSHES_MAIN)
    row2 = "".join(
        f"<button class='btn sm {'primary' if b == brush else ''}' data-brush='{b}'>{lbl}</button>"
        for b, lbl in BRUSHES_EXTRA)
    opts = "".join(f"<option value='{t}' {'selected' if t == brush else ''}>{t}</option>"
                   for t in data.TILE_COLORS)

    return f"""
<div class="card">
  <h2>🗺 Выберите локацию</h2>
  <div style="display:flex;gap:.4rem;flex-wrap:wrap;margin-bottom:1rem;">{tabs}</div>
  <div style="display:flex;align-items:center;gap:.5rem;flex-wrap:wrap">
    <span class="muted">Туман войны глазами игрока:</span>
    <select id="fogPlayerSelect" data-act="world-fog-select" style="max-width:200px;width:auto;">{players}</select>
  </div>
  <div style="margin-top:.7rem">
    <div class="muted" style="margin-bottom:.4rem">🖌 Кисть: ЛКМ рисует и тянется по клеткам,
       ПКМ (или режим «Осмотр») открывает редактор <b>справа</b> — карта не перекрывается.</div>
    <div style="display:flex;gap:6px;flex-wrap:wrap">{row1}</div>
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:4px">{row2}</div>
    <div style="margin-top:.5rem;display:flex;gap:6px;align-items:center;flex-wrap:wrap">
      <span class="muted">Выбрано: <b id="brushLabel">{esc(brush)}</b></span>
      <button class="btn sm primary" id="modePaint">🎨 Рисование</button>
      <button class="btn sm" id="modeInspect">👁️ Осмотр</button>
      <select id="paintBrush" style="display:none">{opts}</select>
    </div>
  </div>
</div>
"""


def _map_card(ctx, li):
    fog_id = ctx.state.get("fog_player", "")
    fog = ctx.store.players.get(int(fog_id)) if fog_id else None
    picked = ctx.state.get("cell_pick", "")

    cells = ""
    for x in range(W.SIZE):
        for y in range(W.SIZE):
            key = f"{li}:{x}:{y}"
            c = ctx.store.world.get(key)
            if not c:
                continue
            here = [p.name[:2] for p in ctx.store.players.values()
                    if p.created_char and p.loc == li and p.x == x and p.y == y]
            if here:
                mark = ("<span style='font-size:0.6rem;font-weight:bold;color:#fff;"
                        "background:var(--accent);padding:1px 2px;border-radius:3px;'>"
                        f"{'|'.join(here)}</span>")
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
            else:
                mark = ""

            style = f"background:{data.TILE_COLORS.get(c.tile, '#333')};"
            if fog and fog.loc == li and (abs(x - fog.x) > 2 or abs(y - fog.y) > 2):
                style += "opacity:0.25; filter:grayscale(80%);"
            css = "c picked" if key == picked else "c"
            # data-act здесь намеренно нет: клик по клетке разбирает кисть в
            # _script(), иначе делегированный обработчик открывал бы редактор
            # на каждый мазок и рисование срывалось.
            cells += (f"<div class='{css}' style='{style}' title='{esc(c.name)} [{x},{y}]' "
                      f"data-key='{key}'>{mark}</div>")

    legend = "".join(f"<span><i class='sw' style='background:{v}'></i>{k}</span>"
                     for k, v in data.TILE_COLORS.items())
    mobs = sum(1 for c in ctx.store.world.values() if c.loc == li and c.mob >= 0)
    chests = sum(1 for c in ctx.store.world.values() if c.loc == li and c.chest)
    walls = sum(1 for c in ctx.store.world.values() if c.loc == li and not c.passable)
    alarm = cataclysm.banner(ctx.store, li)
    alarm_html = f"<div class='cata-live'>{esc(alarm)}</div>" if alarm else ""

    return f"""
<div class="card">
  <h2>{esc(data.LOCATIONS[li][0])}</h2>
  {alarm_html}
  <p class="muted">{esc(data.LOCATIONS[li][1])} · тип: <span class="tag">{data.LOCATIONS[li][2]}</span>
     · мин. уровень {data.LOCATIONS[li][3]}</p>
  <p class="muted" style="margin-bottom:.7rem">👾 мобов: {mobs} · 📦 сундуков: {chests}
     · 🧱 стен: {walls} · ⭐ спавн [{W.SPAWN[0]},{W.SPAWN[1]}]</p>
  <div class="mapgrid" id="locMapGrid">{cells}</div>
  <div class="legend">{legend}</div>
</div>
"""


def _loc_manager(ctx):
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
        badge = f"🏢×{floors}" if floors > 1 else "1 этаж"
        rows += (f"<tr><td>{esc(l[0])} <span style='font-size:0.7rem;color:var(--accent)'>"
                 f"{badge}</span></td><td><span class='tag'>{l[2]}</span></td>"
                 f"<td>{l[3]}+</td><td>[{wx},{wy}]</td>"
                 f"<td>{'🔗 ' + str(len(linked)) if linked else '⚠️ нет'}</td>"
                 f"<td>{players or ''}</td>"
                 f"<td><button class='btn danger sm' data-act='world-loc-del' data-arg='{i}'>🗑</button></td></tr>")
    return f"""
<div class="card">
  <h2>🧭 Локации мира ({len(data.LOCATIONS)})</h2>
  <p class="muted">Новая локация сразу сшивается переходами с соседями по сетке мира.</p>
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


def _regen_card(ctx):
    s = ctx.store.settings
    seeds = W.seeds_of(s)
    saved = s.get("seeds") or {}
    rows = ""
    for key, label, about, _mul in W.SEEDS:
        own = "своё значение" if saved.get(key) else "из базового"
        rows += (f"<div><label>{label} <span class='muted'>· {own}</span></label>"
                 f"<input id='seed_{key}' value='{seeds[key]}' title='{esc(about)}'>"
                 f"<div class='muted' style='font-size:.7rem;margin-top:.15rem'>{esc(about)}</div></div>")
    return f"""
<div class="card">
  <h2>🎲 Сиды мира</h2>
  <div class="hint">Базовый сид задаёт мир целиком. Частные сиды правят свою
     сторону отдельно: перетряхнуть добычу, не трогая рельеф. Пустое поле или
     <code>0</code> — вернуться к выводу из базового.</div>
  <div class="row" style="margin-bottom:.6rem">
    <div><label>🌍 Базовый seed</label><input id="seedInput" value="{s.get('seed', 1337)}"></div>
    <div style="flex:0 0 auto"><label>&nbsp;</label>
      <button class="btn" data-act="world-seeds-roll">🎲 Случайные сиды</button></div>
  </div>
  <div class="row">{rows}</div>
  <div style="margin-top:.9rem;display:flex;gap:.5rem;flex-wrap:wrap">
    <button class="btn primary" data-act="world-seeds-save">💾 Сохранить сиды</button>
    <button class="btn danger" data-act="world-regen">🎲 Перегенерировать мир</button>
  </div>
  <div class="hint warn" style="margin-top:.8rem">Перегенерация пересобирает мир по
     текущим сидам и сетке: позиции игроков сбросятся на спавн, ручные правки клеток пропадут.</div>
</div>
"""


def _script():
    """Кисть по сетке: рисование тянется, правка уходит в боковой док."""
    return """
<script>
(function(){
  const grid = document.getElementById('locMapGrid');
  if (!grid || grid.dataset.wired) return;
  grid.dataset.wired = '1';
  let painting = false, mode = 'paint';
  const sel = () => document.getElementById('paintBrush');
  const brush = () => (sel() ? sel().value : 'grass');

  document.querySelectorAll('[data-brush]').forEach(btn => {
    btn.addEventListener('click', () => {
      const b = btn.dataset.brush;
      if (sel()) sel().value = b;
      const lbl = document.getElementById('brushLabel');
      if (lbl) lbl.textContent = b;
      document.querySelectorAll('[data-brush]').forEach(x => x.classList.remove('primary'));
      btn.classList.add('primary');
      if (window.__app && window.__app.set_brush) window.__app.set_brush(b);
    });
  });

  function setMode(next){
    mode = next;
    const paint = document.getElementById('modePaint');
    const inspect = document.getElementById('modeInspect');
    if (paint) paint.classList.toggle('primary', next === 'paint');
    if (inspect) inspect.classList.toggle('primary', next === 'inspect');
    grid.style.cursor = next === 'paint' ? 'crosshair' : 'pointer';
  }
  const paintBtn = document.getElementById('modePaint');
  const inspectBtn = document.getElementById('modeInspect');
  if (paintBtn) paintBtn.addEventListener('click', () => setMode('paint'));
  if (inspectBtn) inspectBtn.addEventListener('click', () => setMode('inspect'));
  setMode('paint');

  function edit(key){ if (window.__app && window.__app.edit_cell) window.__app.edit_cell(key); }
  function paint(key){
    const b = brush();
    // Дверь и объекты правятся в боковом редакторе — там есть цель перехода.
    if (b === 'door') { edit(key); return; }
    if (window.__app && window.__app.paint_cell) window.__app.paint_cell(key, b);
  }

  grid.addEventListener('mousedown', function(e){
    const cell = e.target.closest('.c');
    if (!cell || e.button === 2) return;
    e.preventDefault();
    if (mode !== 'paint') { edit(cell.dataset.key); return; }
    painting = true;
    paint(cell.dataset.key);
  });
  grid.addEventListener('mouseover', function(e){
    if (!painting || mode !== 'paint') return;
    const cell = e.target.closest('.c');
    if (cell) paint(cell.dataset.key);
  });
  document.addEventListener('mouseup', function(){ painting = false; });
  grid.addEventListener('contextmenu', function(e){
    const cell = e.target.closest('.c');
    if (!cell) return;
    e.preventDefault();
    edit(cell.dataset.key);
  });
  grid.addEventListener('auxclick', function(e){
    if (e.button !== 1) return;
    const cell = e.target.closest('.c');
    if (!cell) return;
    e.preventDefault();
    if (window.__app && window.__app.pick_brush) window.__app.pick_brush(cell.dataset.key);
  });
})();
</script>
"""
