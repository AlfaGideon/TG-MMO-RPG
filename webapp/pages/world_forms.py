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
  👾 Тварей станет <b>вдвое больше</b>, ⚡ шанс засады {int(k['ambush'] * 100)}%,
  ➕ подмога в бой {int(k['join'] * 100)}%.<br>
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
    """Клик по пустой клетке сетки — создаём здесь НОВУЮ локацию.

    Раньше тут предлагался список готовых локаций, и выбор переселял
    существующую — пустая клетка заполнялась ценой опустевшей соседней.
    Переезд остался отдельным делом: drag&drop прямо по сетке.
    """
    return f"""
<h2>➕ Новая локация на [{wx}, {wy}]</h2>
<p class="muted">Клетка сетки свободна — здесь появятся новые земли.
   Переставить уже существующую локацию можно перетаскиванием по сетке.</p>
{loc_fields(ctx, wx, wy)}
<div style="margin-top:1rem;display:flex;gap:.5rem">
  <button class="btn primary" data-act="world-loc-add" data-arg="{wx}:{wy}">💾 Создать здесь</button>
  <button class="btn" data-act="modal-close">Отмена</button>
</div>
"""


def grid_edit_form(ctx, wx, wy, loc_idx):
    """Занятая клетка сетки: правка свойств, снятие с сетки, удаление."""
    loc_idx = int(loc_idx)
    loc = data.LOCATIONS[loc_idx]
    floors = ctx.store.settings.get("location_floors", {}).get(str(loc_idx), 1)
    return f"""
<h2>🌐 {esc(loc[0])} на сетке [{wx}, {wy}]</h2>
<p class="muted">{esc(loc[1])}<br>
   Тип: <span class="tag">{loc[2]}</span> · мин. уровень {loc[3]} · этажей {floors}.</p>
<div class="hint">Переставить локацию — перетащи её по сетке: клетки и
   содержимое переедут вместе с ней.</div>
<div style="margin-top:1rem;display:flex;gap:.5rem;flex-wrap:wrap">
  <button class="btn primary" data-act="world-loc-edit" data-arg="{loc_idx}">✏️ Изменить свойства</button>
  <button class="btn" data-act="world-grid-remove" data-arg="{loc_idx}">📤 Убрать с сетки</button>
  <button class="btn danger" data-act="world-loc-del" data-arg="{loc_idx}">🗑 Удалить локацию</button>
  <button class="btn" data-act="modal-close">Отмена</button>
</div>
"""


TYPES = [("safe", "🛡 Безопасная"), ("dangerous", "⚠️ Опасная"),
         ("dungeon", "💀 Подземелье"), ("boss", "👹 Босс")]


def loc_fields(ctx, wx=None, wy=None, loc=None, floors=1):
    """Поля локации. Общие для создания и правки, чтобы не разъезжались."""
    name = esc(loc[0]) if loc else ""
    desc = esc(loc[1]) if loc else ""
    cur_type = loc[2] if loc else "dangerous"
    level = loc[3] if loc else 1
    type_opts = "".join(
        f"<option value='{v}' {'selected' if v == cur_type else ''}>{label}</option>"
        for v, label in TYPES)
    if wx is None or wy is None:
        grid = ctx.store.settings.get("world_grid", {})
        taken = {tuple(v) for v in grid.values()}
        wx, wy = next(([x, y] for x in range(10) for y in range(10)
                       if (x, y) not in taken), [0, 0])
    coords = f"""
<div class="row" style="margin-top:.5rem">
  <div><label>Мировая X (0-9)</label>
    <input id="loc_wx" type="number" value="{wx}" min="0" max="9"></div>
  <div><label>Мировая Y (0-9)</label>
    <input id="loc_wy" type="number" value="{wy}" min="0" max="9"></div>
</div>""" if loc is None else ""
    return f"""
<div style="margin-top:.7rem"><label>Название</label>
  <input id="loc_name" value="{name}" placeholder="Например: Мглистые топи" required></div>
<div style="margin-top:.5rem"><label>Описание</label>
  <textarea id="loc_desc" rows="2" placeholder="Короткая атмосфера места">{desc}</textarea></div>
<div class="row" style="margin-top:.5rem">
  <div><label>Тип</label><select id="loc_type">{type_opts}</select></div>
  <div><label>Мин. уровень</label>
    <input id="loc_level" type="number" value="{level}" min="1"></div>
  <div><label>Этажей (подуровни)</label>
    <input id="loc_floors" type="number" value="{floors}" min="1" max="10"></div>
</div>{coords}"""


def loc_form(ctx):
    """Мастер добавления новой локации — сразу на сетке мира."""
    return f"""
<h2>➕ Новая локация — сразу на сетке мира</h2>
<p class="muted">Клетки сгенерируются с проверкой связности, двери — <b>одна клетка</b>
   в центре границы. Подуровни визуально — стопка 🏢×N.</p>
{loc_fields(ctx)}
<div style="margin-top:1rem;display:flex;gap:.5rem">
  <button class="btn primary" data-act="world-loc-add">💾 Создать на сетке</button>
  <button class="btn" data-act="modal-close">Отмена</button>
</div>
"""


def loc_edit_form(ctx, li):
    """Правка уже созданной локации: имя, описание, тип, уровень, этажи."""
    li = int(li)
    if li >= len(data.LOCATIONS):
        return "<p>Локация не найдена.</p>"
    loc = data.LOCATIONS[li]
    floors = ctx.store.settings.get("location_floors", {}).get(str(li), 1)
    grid = ctx.store.settings.get("world_grid", {})
    wx, wy = grid.get(str(li), ["—", "—"])
    cells = sum(1 for c in ctx.store.world.values() if c.loc == li)
    players = sum(1 for p in ctx.store.players.values()
                  if p.created_char and p.loc == li)
    return f"""
<h2>✏️ Локация: {esc(loc[0])}</h2>
<p class="muted">Место на сетке [{wx},{wy}] · клеток: {cells} · игроков: {players}.
   Клетки и швы не пересобираются — правятся только свойства локации.
   Переставить на сетке можно перетаскиванием во вкладке «Сетка мира».</p>
{loc_fields(ctx, loc=loc, floors=floors)}
<div style="margin-top:1rem;display:flex;gap:.5rem;flex-wrap:wrap">
  <button class="btn primary" data-act="world-loc-save" data-arg="{li}">💾 Сохранить</button>
  <button class="btn danger" data-act="world-loc-del" data-arg="{li}">🗑 Удалить</button>
  <button class="btn" data-act="modal-close">Отмена</button>
</div>
"""
