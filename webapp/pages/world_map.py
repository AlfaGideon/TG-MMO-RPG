"""Карта локации: выбор локации стрелками и боковой редактор клетки.

Локации переключаются «крестом» стрелок вокруг текущей: ▲ север, ▼ юг,
◀ запад, ▶ восток — ровно так, как локации стоят на сетке мира. Список
кнопок с названиями убран: он разрастался с каждой новой локацией и не
показывал, где эти земли находятся относительно друг друга.

Кисти и переключателя тумана войны здесь больше нет: рисование по сетке
конфликтовало с редактором клетки и работало через раз, а туман глазами
игрока ничего не менял в самой панели. Клетка правится в доке справа.
"""
from engine import cataclysm, data, world as W
from webapp.html import esc
from webapp.pages import world_forms as forms

# Стороны света: ключ → (подпись, смещение по сетке мира, класс в кресте)
DIRS = [("north", "▲", (0, -1), "up"), ("west", "◀", (-1, 0), "left"),
        ("east", "▶", (1, 0), "right"), ("south", "▼", (0, 1), "down")]


def render(ctx):
    li = ctx.state.get("loc", 0)
    if li >= len(data.LOCATIONS):
        li = 0
        ctx.state["loc"] = 0

    return f"""
{_picker(ctx, li)}
<div class="mapdock">
  {_map_card(ctx, li)}
  <div class="dock" id="cellDock">{forms.cell_form(ctx, ctx.state.get("cell_pick", ""))}</div>
</div>
{_script()}
{_loc_manager(ctx)}
{_regen_card(ctx)}
"""


# ── выбор локации стрелками ─────────────────────────────────

def _grid_pos(ctx):
    """Раскладка локаций по сетке мира: {индекс: (wx, wy)}."""
    grid = ctx.store.settings.get("world_grid", {}) or {}
    out = {}
    for key, xy in grid.items():
        try:
            idx = int(key)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(data.LOCATIONS) and xy and len(xy) >= 2:
            out[idx] = (int(xy[0]), int(xy[1]))
    return out


def neighbours(ctx, li):
    """Соседи локации по сторонам света: {'north': idx|None, ...}.

    Локация вне сетки мира соседей не имеет — для неё ◀ и ▶ листают
    список по порядку, иначе до неё было бы не добраться стрелками.
    """
    pos = _grid_pos(ctx)
    here = pos.get(li)
    out = {key: None for key, _lbl, _d, _css in DIRS}
    if here is None:
        total = len(data.LOCATIONS)
        if total > 1:
            out["west"] = (li - 1) % total
            out["east"] = (li + 1) % total
        return out, None
    for key, _lbl, (dx, dy), _css in DIRS:
        want = (here[0] + dx, here[1] + dy)
        out[key] = next((i for i, xy in pos.items() if xy == want), None)
    return out, here


def _arrow(css, label, target, hint):
    if target is None:
        return (f"<button class='locnav-btn {css}' disabled title='{esc(hint)}'>"
                f"<span class='locnav-sign'>{label}</span>"
                f"<span class='locnav-name muted'>— нет —</span></button>")
    name = data.LOCATIONS[target][0]
    return (f"<button class='locnav-btn {css}' data-act='world-loc' data-arg='{target}' "
            f"title='{esc(hint)}: {esc(name)}'>"
            f"<span class='locnav-sign'>{label}</span>"
            f"<span class='locnav-name'>{esc(name)}</span></button>")


def _picker(ctx, li):
    near, here = neighbours(ctx, li)
    loc = data.LOCATIONS[li]
    floors = max(1, int((ctx.store.settings.get("location_floors", {}) or {})
                        .get(str(li), 1) or 1))
    players = sum(1 for p in ctx.store.players.values()
                  if p.created_char and p.loc == li)
    where = (f"сетка [{here[0]},{here[1]}]" if here
             else "<span class='warn-text'>не на сетке мира</span>")
    hints = {"north": "Севернее", "south": "Южнее",
             "west": "Западнее", "east": "Восточнее"}
    if here is None:
        hints["west"], hints["east"] = "Предыдущая по списку", "Следующая по списку"

    cross = "".join(_arrow(css, label, near[key], hints[key])
                    for key, label, _d, css in DIRS)
    total = len(data.LOCATIONS)
    return f"""
<div class="card">
  <h2>🗺 Выберите локацию</h2>
  <p class="muted">Стрелки ведут к соседям по сетке мира: ▲ север, ▼ юг,
     ◀ запад, ▶ восток. Локация {li + 1} из {total}.</p>
  <div class="locnav">
    {cross}
    <div class="locnav-cur cur">
      <div class="locnav-title">{esc(loc[0])}</div>
      <div class="muted locnav-meta">
        <span class="tag">{esc(loc[2])}</span> · ур. {loc[3]}+ · {where}
        · 🏢 {floors} · 👥 {players}
      </div>
    </div>
  </div>
</div>
"""


# ── карта локации ───────────────────────────────────────────

def _map_card(ctx, li):
    picked = ctx.state.get("cell_pick", "")

    # Один слой — одна сетка. Накладывать этажи друг на друга нельзя: клетки
    # имеют одинаковые координаты и раньше при этом всегда читался этаж 0.
    floors_map = ctx.store.settings.get("location_floors", {})
    loc_floors = max(1, int(floors_map.get(str(li), 1) or 1))
    try:
        active_floor = int(ctx.state.get("floor_filter", "0"))
    except (TypeError, ValueError):
        active_floor = 0
    active_floor = min(max(active_floor, 0), loc_floors - 1)

    cells = ""
    for x in range(W.SIZE):
        for y in range(W.SIZE):
            c = W.cell_at(ctx.store.world, li, x, y, active_floor)
            if not c:
                continue
            key = c.key
            cell_floor = getattr(c, "floor", 0) or 0
            here = [p for p in ctx.store.players.values()
                    if p.created_char and p.loc == li and p.x == x and p.y == y]
            # Показываем на сетке только персонажей выбранного этажа.
            here = [p for p in here if (getattr(p, "floor", 0) or 0) == active_floor]
            if here:
                names = "|".join(p.name[:2] for p in here)
                mark = (f"<span style='font-size:0.6rem;font-weight:bold;color:#fff;"
                        f"background:var(--accent);padding:1px 2px;border-radius:3px;'>"
                        f"{names}</span>")
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
            css = "c picked" if key == picked else "c"
            cells += (f"<div class='{css}' style='{style}' title='{esc(c.name)} [{x},{y}] эт.{cell_floor}' "
                      f"data-key='{key}'>{mark}</div>")

    legend = "".join(f"<span><i class='sw' style='background:{v}'></i>{k}</span>"
                     for k, v in data.TILE_COLORS.items())
    mobs = sum(1 for c in ctx.store.world.values() if c.loc == li and c.mob >= 0)
    chests = sum(1 for c in ctx.store.world.values() if c.loc == li and c.chest)
    walls = sum(1 for c in ctx.store.world.values() if c.loc == li and not c.passable)
    alarm = cataclysm.banner(ctx.store, li)
    alarm_html = f"<div class='cata-live'>{esc(alarm)}</div>" if alarm else ""

    # Переключатели расположены рядом с сеткой: так карта не сдвигается вниз.
    floor_buttons = ""
    if loc_floors > 1:
        for f in range(loc_floors):
            css = "primary" if active_floor == f else ""
            cnt = sum(1 for p in ctx.store.players.values()
                      if p.created_char and p.loc == li and (getattr(p, "floor", 0) or 0) == f)
            badge = f" ({cnt})" if cnt else ""
            floor_buttons += (f"<button class='btn sm {css}' data-act='world-floor' "
                              f"data-arg='{f}'>Этаж {f}{badge}</button>")

    # Список игроков на локации с этажами
    loc_players = [p for p in ctx.store.players.values() if p.created_char and p.loc == li]
    loc_players = [p for p in loc_players
                   if (getattr(p, "floor", 0) or 0) == active_floor]
    players_html = ""
    if loc_players:
        rows = "".join(
            f"<div style='display:flex;align-items:center;gap:.5rem;padding:.35rem .5rem;background:var(--bg-dark);border:1px solid var(--border);border-radius:6px;'>"
            f"<span style='font-size:.7rem;padding:2px 6px;border-radius:999px;background:var(--accent-soft);color:var(--accent);font-weight:600;'>Этаж {getattr(p, 'floor', 0) or 0}</span>"
            f"<span style='font-weight:600;flex:1;'>{esc(p.name)}</span>"
            f"<span class='muted' style='font-size:.75rem;'>Ур.{p.level} [{p.x},{p.y}]</span>"
            f"</div>" for p in loc_players
        )
        players_html = f"""
<div style="margin-top:.8rem;">
  <h3 style="margin-bottom:.4rem;">👥 Игроки на локации ({len(loc_players)})</h3>
  <div style="display:flex;flex-direction:column;gap:.3rem;">{rows}</div>
</div>"""

    return f"""
<div class="card">
  <h2>{esc(data.LOCATIONS[li][0])} {f'<span class="tag" style="font-size:.7rem;">🏢 {loc_floors} этажей</span>' if loc_floors > 1 else ''}</h2>
  {alarm_html}
  <p class="muted">{esc(data.LOCATIONS[li][1])} · тип: <span class="tag">{data.LOCATIONS[li][2]}</span>
     · мин. уровень {data.LOCATIONS[li][3]}</p>
  <p class="muted" style="margin-bottom:.7rem">👾 мобов: {mobs} · 📦 сундуков: {chests}
     · 🧱 стен: {walls} · ⭐ спавн [{W.SPAWN[0]},{W.SPAWN[1]}]</p>
  <div class="floor-map-layout">
    <div class="mapgrid" id="locMapGrid">{cells}</div>
    {f'<div class="floor-switcher" aria-label="Этаж карты">{floor_buttons}</div>' if loc_floors > 1 else ''}
  </div>
  <p class="muted" style="margin-top:.6rem">🖱 Клик по клетке — правка в доке справа.</p>
  <div class="legend">{legend}</div>
  {players_html}
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
        rows += (f"<tr><td><button class='linklike' data-act='world-loc' data-arg='{i}' "
                 f"title='Открыть карту этой локации'>{esc(l[0])}</button> "
                 f"<span style='font-size:0.7rem;color:var(--accent)'>"
                 f"{badge}</span><div class='muted' style='font-size:.72rem'>"
                 f"{esc(l[1][:60])}</div></td>"
                 f"<td><span class='tag'>{l[2]}</span></td>"
                 f"<td>{l[3]}+</td><td>[{wx},{wy}]</td>"
                 f"<td>{'🔗 ' + str(len(linked)) if linked else '⚠️ нет'}</td>"
                 f"<td>{players or ''}</td>"
                 f"<td style='white-space:nowrap'>"
                 f"<button class='btn sm' data-act='world-loc-edit' data-arg='{i}' "
                 f"title='Изменить название, описание, тип, уровень, этажи'>✏️</button> "
                 f"<button class='btn danger sm' data-act='world-loc-del' data-arg='{i}'>🗑</button>"
                 f"</td></tr>")
    return f"""
<div class="card">
  <h2>🧭 Локации мира ({len(data.LOCATIONS)})</h2>
  <p class="muted">Клик по названию открывает карту локации — на случай, если
     до неё не дотянуться стрелками. ✏️ правит свойства (клетки и швы остаются
     на месте), 🗑 удаляет её и переиндексирует мир.</p>
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
    """Клик по клетке открывает её в боковом доке.

    Своим обработчиком, а не через data-act: делегированный клик всего
    документа ходит по всем ста клеткам и тормозит панель.
    """
    return """
<script>
(function(){
  const grid = document.getElementById('locMapGrid');
  if (!grid || grid.dataset.wired) return;
  grid.dataset.wired = '1';
  grid.style.cursor = 'pointer';
  function edit(key){ if (window.__app && window.__app.edit_cell) window.__app.edit_cell(key); }
  grid.addEventListener('click', function(e){
    const cell = e.target.closest('.c');
    if (!cell) return;
    e.preventDefault();
    edit(cell.dataset.key);
  });
  grid.addEventListener('contextmenu', function(e){
    const cell = e.target.closest('.c');
    if (!cell) return;
    e.preventDefault();
    edit(cell.dataset.key);
  });
})();
</script>
"""
