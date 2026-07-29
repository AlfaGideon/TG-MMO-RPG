"""Страница «Мир»: вкладки карты, сетки, подземелий и катаклизмов.

Сам рендер разнесён по соседним модулям, чтобы файлы оставались читаемыми:
`world_map` — карта локации с кистью и боковым редактором клетки,
`world_grid` — мировая сетка 10×10,
`world_cataclysms` — бедствия,
`dungeons` — порталы.
"""
from webapp.pages import dungeons as page_dungeons
from webapp.pages import world_cataclysms as page_cata
from webapp.pages import world_forms as forms
from webapp.pages import world_grid as page_grid
from webapp.pages import world_map as page_map

TITLE = "🗺 Мир"
CRUMBS = [("Мир", "world")]

# Формы живут в world_forms.py; отсюда их забирают действия.
cell_form = forms.cell_form
grid_place_form = forms.grid_place_form
grid_edit_form = forms.grid_edit_form
loc_form = forms.loc_form
loc_edit_form = forms.loc_edit_form
cataclysm_form = forms.cataclysm_form

TABS = [
    ("map", "🗺 Локации"),
    ("grid", "🌐 Сетка мира (10x10)"),
    ("cataclysms", "🌋 Катаклизмы"),
    ("dungeons", "🗝 Подземелья & Порталы"),
]

RENDERERS = {
    "map": page_map.render,
    "grid": page_grid.render,
    "cataclysms": page_cata.render,
    "dungeons": page_dungeons.render,
}


def render(ctx):
    tab = ctx.state.setdefault("world_tab", "map")
    if tab not in RENDERERS:
        tab = "map"

    live = len(ctx.store.settings.get("cataclysms") or [])
    buttons = ""
    for key, label in TABS:
        if key == "cataclysms" and live:
            label += f" <b>({live}🔥)</b>"
        css = "btn primary" if key == tab else "btn"
        buttons += (f"<button class='{css}' data-act='world-tab' "
                    f"data-arg='{key}'>{label}</button> ")

    return f"""
<div class="card">
  <h2>🗺 Разделы мира</h2>
  <div style="margin-bottom:.5rem;display:flex;gap:.4rem;flex-wrap:wrap">{buttons}</div>
</div>
{RENDERERS[tab](ctx)}
"""
