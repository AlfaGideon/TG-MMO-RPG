"""Действия вкладок «Мир» и «Настройки»."""
import json
import random

from engine import adminops, world as W, data
from webapp import dom
from webapp.pages import dungeons as page_dungeons
from webapp.pages import world as page

DEFAULTS = {"token": "", "seed": 1337, "welcome_bonus": 50,
            "proxy_mode": "direct", "proxy_url": ""}


def register(app, A):
    A("world-loc", lambda arg: _pick_loc(app, arg))
    A("world-regen", lambda _="": _regen(app))
    A("cell-edit", lambda arg: app.modal(page.cell_form(app, arg)))
    A("cell-save", lambda arg: _cell_save(app, arg))
    A("data-export", lambda _="": _export(app))
    A("data-reset", lambda _="": _reset(app))
    A("settings-save", lambda _="": _settings_save(app))
    A("panel-url-save", lambda _="": _panel_url_save(app))
    
    # New overhauled actions
    A("world-tab", lambda arg: _pick_tab(app, arg))
    A("world-fog-select", lambda _="": _fog_select(app))
    A("world-grid-place", lambda arg: _grid_place(app, arg))
    A("world-grid-edit", lambda arg: _grid_edit(app, arg))
    A("world-grid-save", lambda arg: _grid_save(app, arg))
    A("world-grid-remove", lambda arg: _grid_remove(app, arg))
    A("dungeon-create", lambda _="": _dungeon_create(app))
    A("dungeon-open", lambda arg: _dungeon_open(app, arg))
    A("dungeon-close", lambda arg: _dungeon_close(app, arg))
    A("dungeon-delete", lambda arg: _dungeon_delete(app, arg))
    A("portal-loc", lambda arg: _portal_loc(app, arg))
    A("dungeon-focus", lambda arg: _dungeon_focus(app, arg))


def _pick_loc(app, idx):
    app.state["loc"] = int(idx)
    app.render()


def _regen(app):
    from js import window
    if not window.confirm("Пересоздать мир? Позиции игроков сбросятся."):
        return
    try:
        seed = int(dom.value("#seedInput", "1337"))
    except ValueError:
        seed = 1337
    app.store.regen_world(seed)
    for p in app.store.players.values():
        p.loc, p.x, p.y = 0, W.SPAWN[0], W.SPAWN[1]
    app.store.save()
    app.bot.game.world = app.store.world
    dom.toast(f"Мир пересоздан (seed {seed})")
    app.render()


def _cell_save(app, key):
    c = app.store.world.get(key)
    if not c:
        return
    c.name = dom.value("#cf_name", c.name)
    c.desc = dom.value("#cf_desc", c.desc)
    c.tile = dom.value("#cf_tile", c.tile)
    c.passable = dom.value("#cf_pass", "1") == "1"
    c.chest = dom.value("#cf_chest", "0") == "1"
    c.mob = int(dom.value("#cf_mob", "-1"))
    c.npc = int(dom.value("#cf_npc", "-1"))
    app.store.save()
    app.close_modal()
    dom.toast("Клетка сохранена")
    app.render()


def _export(app):
    dom.set_value("#ioBox", app.store.backend.get("shadowlands") or "{}")
    dom.toast("Экспортировано в поле ниже")


def _reset(app):
    from js import window
    if not window.confirm("Стереть ВСЁ: игроков, мир и токен?"):
        return
    app.store.backend.clear("shadowlands")
    app.store.players = {}
    app.store.settings = dict(DEFAULTS)
    app.store.regen_world()
    app.bot.game.world = app.store.world
    app.bot.transport.settings = app.store.settings
    dom.toast("Сброшено")
    app.render()


def _settings_save(app):
    try:
        app.store.settings["seed"] = int(dom.value("#setSeed", "1337"))
        app.store.settings["welcome_bonus"] = int(dom.value("#setGold", "50"))
    except ValueError:
        dom.toast("Числа, пожалуйста", "err")
        return
    app.store.save()
    dom.toast("Настройки сохранены")


def _panel_url_save(app):
    """Адрес панели для инлайн-кнопки «Открыть панель» в боте."""
    from engine.permissions import normalize_url

    url = normalize_url(dom.value("#panelUrl", ""))
    app.store.settings["panel_url"] = url
    app.store.save()
    dom.toast("Адрес панели сохранён" if url else "Адрес панели очищен")
    app.render()


def _pick_tab(app, tab):
    app.state["world_tab"] = tab
    app.render()


def _fog_select(app):
    app.state["fog_player"] = dom.value("#fogPlayerSelect", "")
    app.render()


def _grid_place(app, arg):
    wx, wy = map(int, arg.split(":"))
    app.modal(page.grid_place_form(app, wx, wy))


def _grid_edit(app, arg):
    wx, wy, loc_idx = map(int, arg.split(":"))
    app.modal(page.grid_edit_form(app, wx, wy, loc_idx))


def _grid_save(app, arg):
    wx, wy = map(int, arg.split(":"))
    try:
        loc_idx = int(dom.value("#grid_loc_idx", "0"))
    except ValueError:
        return
        
    grid = app.store.settings.setdefault("world_grid", {})
    # remove location from any previous coord
    for k, v in list(grid.items()):
        if int(k) == loc_idx:
            grid.pop(k, None)
            
    grid[str(loc_idx)] = [wx, wy]
    app.store.save()
    app.close_modal()
    dom.toast("Локация размещена на сетке")
    app.render()


def _grid_remove(app, loc_idx):
    grid = app.store.settings.setdefault("world_grid", {})
    grid.pop(str(loc_idx), None)
    app.store.save()
    app.close_modal()
    dom.toast("Локация убрана с сетки")
    app.render()


def _portal_loc(app, idx):
    """Переключает локацию на карте порталов."""
    app.state["world_tab"] = "dungeons"
    app.state["portal_loc"] = int(idx)
    app.render()


def _dungeon_focus(app, dg_id):
    """Клик по 🌀 на карте — карточка подземелья."""
    tpls = app.store.settings.setdefault("dungeon_templates", [])
    dg = next((t for t in tpls if t["id"] == int(dg_id)), None)
    if not dg:
        dom.toast("Шаблон не найден", "err")
        return
    app.modal(page_dungeons.dungeon_form(app, dg))


def _dungeon_create(app):
    name = dom.value("#dg_name").strip()
    desc = dom.value("#dg_desc").strip() or "Загадочные катакомбы."
    try:
        min_level = int(dom.value("#dg_level", "1"))
        grid_size = int(dom.value("#dg_size", "10"))
    except ValueError:
        dom.toast("Уровень и размер должны быть числами", "err")
        return
        
    if not name:
        dom.toast("Введите название!", "err")
        return
        
    tpls = app.store.settings.setdefault("dungeon_templates", [])
    new_id = max([t["id"] for t in tpls] + [-1]) + 1
    tpls.append({
        "id": new_id,
        "name": name,
        "desc": desc,
        "min_level": min_level,
        "grid_size": grid_size,
        "portal_cell": None
    })
    app.store.save()
    dom.toast("Шаблон подземелья создан!")
    app.render()


def _dungeon_open(app, dg_id):
    from engine import adminmenu
    try:
        _, info = adminops.portal_open(app.store, app.actor, dg_id,
                                       adminmenu.pick_cell)
    except adminops.Denied as e:
        dom.toast(str(e), "err")
        return
    app.log("sys", f"📢 Портал открыт: {info}")
    dom.toast("Портал успешно открыт!")
    app.render()
    _flush(app)


def _dungeon_close(app, dg_id):
    try:
        adminops.portal_close(app.store, app.actor, dg_id)
    except adminops.Denied as e:
        dom.toast(str(e), "err")
        return
    app.log("sys", "❌ Портал закрыт администратором.")
    dom.toast("Портал закрыт")
    app.render()
    _flush(app)


def _flush(app):
    if not getattr(app.bot, "running", False):
        return
    import asyncio
    asyncio.ensure_future(app.bot.flush_outbox())


def _dungeon_delete(app, dg_id):
    from js import window
    if not window.confirm("Удалить этот шаблон подземелья?"):
        return
        
    _dungeon_close(app, dg_id)
    tpls = app.store.settings.setdefault("dungeon_templates", [])
    app.store.settings["dungeon_templates"] = [t for t in tpls if t["id"] != int(dg_id)]
    app.store.save()
    dom.toast("Шаблон подземелья удалён")
    app.render()
