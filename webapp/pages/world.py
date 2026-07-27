"""Страница: карта мира и редактор клеток."""
from engine import data, world as W
from webapp.html import esc

TITLE = "🗺 Мир"


def render(ctx):
    li = ctx.state.get("loc", 0)
    tabs = "".join(
        f"<button class='btn {'primary' if i == li else ''}' data-act='world-loc' data-arg='{i}'>"
        f"{esc(l[0])}</button>" for i, l in enumerate(data.LOCATIONS))

    cells = ""
    for x in range(W.SIZE):
        for y in range(W.SIZE):
            c = ctx.store.world.get(f"{li}:{x}:{y}")
            if not c:
                continue
            color = data.TILE_COLORS.get(c.tile, "#333")
            mark = ""
            if c.link:
                mark = "🚪"
            elif c.mob >= 0:
                mark = "👾"
            elif c.npc >= 0:
                mark = "💬"
            elif c.chest:
                mark = "📦"
            elif (x, y) == W.SPAWN:
                mark = "⭐"
            cells += (f"<div class='c' style='background:{color}' title='{esc(c.name)} [{x},{y}]' "
                      f"data-act='cell-edit' data-arg='{li}:{x}:{y}'>{mark}</div>")

    legend = "".join(f"<span><i class='sw' style='background:{v}'></i>{k}</span>"
                     for k, v in data.TILE_COLORS.items())
    mobs = sum(1 for c in ctx.store.world.values() if c.loc == li and c.mob >= 0)
    chests = sum(1 for c in ctx.store.world.values() if c.loc == li and c.chest)
    walls = sum(1 for c in ctx.store.world.values() if c.loc == li and not c.passable)

    return f"""
<div class="card">
  <h2>🗺 Локации</h2>
  <div style="display:flex;gap:.4rem;flex-wrap:wrap">{tabs}</div>
</div>

<div class="card">
  <h2>{esc(data.LOCATIONS[li][0])}</h2>
  <p class="muted">{esc(data.LOCATIONS[li][1])} · тип: <span class="tag">{data.LOCATIONS[li][2]}</span>
     · мин. уровень {data.LOCATIONS[li][3]}</p>
  <p class="muted" style="margin-bottom:.7rem">👾 мобов: {mobs} · 📦 сундуков: {chests} · 🧱 стен: {walls}
     · ⭐ спавн [{W.SPAWN[0]},{W.SPAWN[1]}] · 🚪 переход в соседнюю локацию</p>
  <div class="mapgrid">{cells}</div>
  <div class="legend">{legend}</div>
  <p class="muted" style="margin-top:.6rem">Клик по клетке — редактировать.</p>
</div>

<div class="card">
  <h2>🎲 Пересоздать мир</h2>
  <div class="hint warn">Мир будет сгенерирован заново. Позиции игроков сбросятся на спавн.</div>
  <div class="row">
    <div><label>Seed</label><input id="seedInput" value="{ctx.store.settings.get('seed',1337)}"></div>
    <div style="flex:0 0 auto"><button class="btn danger" data-act="world-regen">🎲 Перегенерировать</button></div>
  </div>
</div>
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
<div style="margin-top:.7rem"><label>Название</label><input id="cf_name" value="{esc(c.name)}"></div>
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
"""
