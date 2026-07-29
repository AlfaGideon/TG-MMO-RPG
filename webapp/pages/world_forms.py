"""Формы вкладки «Мир»: клетка (боковой док), сетка, локация, катаклизм."""
from engine import cataclysm as C
from engine import data
from webapp.html import esc


def cell_form(ctx, key):
    """Редактор клетки для правой колонки карты.

    Отдельного окна нет: форма живёт рядом с сеткой, поэтому кисть по клеткам
    работает без помех, а выбранная клетка подсвечивается прямо на карте.
    """
    c = ctx.store.world.get(key) if key else None
    if not c:
        return """
<h2>🔧 Редактор клетки</h2>
<div class="dock-empty">
  Клетка не выбрана.<br><br>
  🎨 <b>Рисование</b> — ЛКМ красит выбранной кистью, можно тянуть.<br>
  👁️ <b>Осмотр</b> или ПКМ — открыть клетку здесь.<br>
  🖱 Средняя кнопка — пипетка: подобрать кисть с клетки.
</div>
"""
    tiles = "".join(f"<option {'selected' if t == c.tile else ''}>{t}</option>"
                    for t in data.TILE_COLORS)
    mobs = "<option value='-1'>— нет —</option>" + "".join(
        f"<option value='{i}' {'selected' if i == c.mob else ''}>{esc(m[0])} (ур.{m[2]})</option>"
        for i, m in enumerate(data.MOBS))
    npcs = "<option value='-1'>— нет —</option>" + "".join(
        f"<option value='{i}' {'selected' if i == c.npc else ''}>{esc(n[0])}</option>"
        for i, n in enumerate(data.NPCS))
    link_note = ("<p class='muted' style='margin-top:.5rem'>🚪 Клетка-переход в «"
                 + esc(data.LOCATIONS[c.link[0]][0]) + "»</p>") if c.link else ""

    return f"""
<div class="dock-head">
  <h2 style="margin:0">🔧 [{c.x},{c.y}] · {esc(data.LOCATIONS[c.loc][0])}</h2>
  <button class="dock-close" data-act="cell-close" title="Снять выделение">✕</button>
</div>
<form data-validate>
<div><label>Название</label><input id="cf_name" value="{esc(c.name)}" required></div>
<div style="margin-top:.5rem"><label>Описание</label>
  <textarea id="cf_desc" rows="3">{esc(c.desc)}</textarea></div>
<div style="margin-top:.5rem"><label>Тайл</label><select id="cf_tile">{tiles}</select></div>
<div class="row" style="margin-top:.5rem">
  <div><label>Проходима</label><select id="cf_pass">
     <option value="1" {'selected' if c.passable else ''}>да</option>
     <option value="0" {'selected' if not c.passable else ''}>нет</option></select></div>
  <div><label>Сундук</label><select id="cf_chest">
     <option value="1" {'selected' if c.chest else ''}>есть</option>
     <option value="0" {'selected' if not c.chest else ''}>нет</option></select></div>
</div>
<div style="margin-top:.5rem"><label>Моб</label><select id="cf_mob">{mobs}</select></div>
<div style="margin-top:.5rem"><label>NPC</label><select id="cf_npc">{npcs}</select></div>
{link_note}
<div style="margin-top:1rem;display:flex;gap:.5rem;flex-wrap:wrap">
  <button class="btn primary" data-act="cell-save" data-arg="{key}">💾 Сохранить</button>
  <button class="btn" data-act="cell-close">Закрыть</button>
</div>
</form>
"""


def cataclysm_form(ctx, kind_key):
    k = C.kind(kind_key)
    if not k:
        return "<p>Неизвестный катаклизм.</p>"
    locs = f"<option value='{C.GLOBAL}'>🌍 Весь мир</option>" + "".join(
        f"<option value='{i}'>{esc(l[0])}</option>" for i, l in enumerate(data.LOCATIONS))
    return f"""
<h2>{k['icon']} Наслать: {esc(k['name'])}</h2>
<p class="muted" style="margin-top:.4rem">{esc(k['omen'])}<br>{esc(k['story'])}</p>
<div class="hint" style="margin-top:.7rem">
  Охват ~{int(k['spread'] * 100)}% клеток · 👾×{k['mob_rate']:.2f} · 💥×{k['damage']:.2f}
  · 📦×{k['loot']:.2f} · 🪙×{k['gold']:.2f} · 🏕×{k['rest']:.2f}<br>
  Клетки под игроками, спавн и переходы между локациями не пострадают.
</div>
<div class="row" style="margin-top:.6rem">
  <div><label>Где</label><select id="cata_loc">{locs}</select></div>
  <div><label>Часов</label>
    <input id="cata_hours" type="number" min="1" max="48" step="1" value="{k['hours']}"></div>
</div>
<div style="margin-top:1rem;display:flex;gap:.5rem">
  <button class="btn danger" data-act="cata-strike" data-arg="{kind_key}">🌋 Обрушить</button>
  <button class="btn" data-act="modal-close">Отмена</button>
</div>
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


def loc_form(ctx):
    """Мастер добавления новой локации — сразу на сетке мира."""
    types = [("safe", "🛡 Безопасная"), ("dangerous", "⚠️ Опасная"),
             ("dungeon", "💀 Подземелье"), ("boss", "👹 Босс")]
    type_opts = "".join(f"<option value='{v}'>{label}</option>" for v, label in types)
    grid = ctx.store.settings.get("world_grid", {})
    taken = {tuple(v) for v in grid.values()}
    free = next(([x, y] for x in range(10) for y in range(10)
                 if (x, y) not in taken), [0, 0])
    return f"""
<h2>➕ Новая локация — сразу на сетке мира</h2>
<p class="muted">Клетки сгенерируются с проверкой связности, двери — <b>одна клетка</b>
   в центре границы. Подуровни визуально — стопка 🏢×N.</p>
<div style="margin-top:.7rem"><label>Название</label>
  <input id="loc_name" placeholder="Например: Мглистые топи" required></div>
<div style="margin-top:.5rem"><label>Описание</label>
  <textarea id="loc_desc" rows="2" placeholder="Короткая атмосфера места"></textarea></div>
<div class="row" style="margin-top:.5rem">
  <div><label>Тип</label><select id="loc_type">{type_opts}</select></div>
  <div><label>Мин. уровень</label><input id="loc_level" type="number" value="1" min="1"></div>
  <div><label>Этажей (подуровни)</label><input id="loc_floors" type="number" value="1" min="1" max="10"></div>
</div>
<div class="row" style="margin-top:.5rem">
  <div><label>Мировая X (0-9)</label><input id="loc_wx" type="number" value="{free[0]}" min="0" max="9"></div>
  <div><label>Мировая Y (0-9)</label><input id="loc_wy" type="number" value="{free[1]}" min="0" max="9"></div>
</div>
<div style="margin-top:1rem;display:flex;gap:.5rem">
  <button class="btn primary" data-act="world-loc-add">💾 Создать на сетке</button>
  <button class="btn" data-act="modal-close">Отмена</button>
</div>
"""
