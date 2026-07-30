"""Действия вкладки «Мир»: карта, клетки, сетка, сиды."""
import random

from engine import world as W
from webapp import dom
from webapp.actions import (cataclysm_actions, living_actions,
                            settings_actions)
from webapp.pages import world as page

def register(app, A):
    A("world-tab", lambda arg: _pick_tab(app, arg))
    A("world-loc", lambda arg: _pick_loc(app, arg))
    A("world-floor", lambda arg: _pick_floor(app, arg))
    A("world-fog-select", lambda _="": _fog_select(app))
    A("world-regen", lambda _="": _regen(app))
    A("world-seeds-save", lambda _="": _seeds_save(app))
    A("world-seeds-roll", lambda _="": _seeds_roll(app))

    A("cell-close", lambda _="": _cell_close(app))
    A("cell-save", lambda arg: _cell_save(app, arg))

    A("world-grid-place", lambda arg: _grid_place(app, arg))
    A("world-grid-edit", lambda arg: _grid_edit(app, arg))
    A("world-grid-remove", lambda arg: _grid_remove(app, arg))
    A("world-relink", lambda _="": _relink(app))
    A("world-shuffle", lambda _="": _grid_shuffle(app))

    A("world-loc-new", lambda _="": app.modal(page.loc_form(app)))
    A("world-loc-add", lambda arg="": _loc_add(app, arg))
    A("world-loc-edit", lambda arg: app.modal(page.loc_edit_form(app, arg)))
    A("world-loc-save", lambda arg: _loc_save(app, int(arg)))
    A("world-loc-del", lambda arg: _loc_del(app, int(arg)))

    cataclysm_actions.register(app, A)
    living_actions.register(app, A)
    settings_actions.register(app, A)


# ── навигация ───────────────────────────────────────────────

def _pick_tab(app, tab):
    app.state["world_tab"] = tab
    app.render()


def _pick_loc(app, idx):
    app.state["loc"] = int(idx)
    app.state["cell_pick"] = ""        # выделение чужой локации ни к чему
    app.state["floor_filter"] = "0"     # у новой локации всегда открываем первый этаж
    app.render()


def _pick_floor(app, floor):
    """Показывает отдельную сетку выбранного этажа."""
    app.state["floor_filter"] = str(floor)
    app.state["cell_pick"] = ""
    app.render()


def _fog_select(app):
    app.state["fog_player"] = dom.value("#fogPlayerSelect", "")
    app.render()


# ── клетки ──────────────────────────────────────────────────

def _cell_edit(app, key):
    """Показать клетку в боковом редакторе (док справа от карты).

    Зовётся из inline-JS карты, а не через data-act: делегированный клик
    срабатывал бы на каждом мазке кистью и сбивал рисование.
    """
    if key not in app.store.world:
        dom.toast("Клетка не найдена", "err")
        return
    app.state["cell_pick"] = key
    app.render()


def _cell_close(app):
    app.state["cell_pick"] = ""
    app.render()


def _cell_save(app, key):
    c = app.store.world.get(key)
    if not c:
        dom.toast("Клетка не найдена", "err")
        return
    c.name = dom.value("#cf_name", c.name)
    c.desc = dom.value("#cf_desc", c.desc)
    c.tile = dom.value("#cf_tile", c.tile)
    c.passable = dom.value("#cf_pass", "1") == "1"
    c.chest = dom.value("#cf_chest", "0") == "1"
    c.mob = int(dom.value("#cf_mob", "-1"))
    c.npc = int(dom.value("#cf_npc", "-1"))
    app.store.save()
    dom.toast(f"Клетка [{c.x},{c.y}] сохранена")
    app.render()


# ── сиды и пересоздание ─────────────────────────────────────

def _regen(app):
    from js import window
    if not window.confirm("Пересоздать мир? Позиции игроков сбросятся."):
        return
    _collect_seeds(app)
    try:
        seed = int(dom.value("#seedInput", "1337"))
    except ValueError:
        seed = 1337
    app.store.regen_world(seed)
    for p in app.store.players.values():
        p.loc, p.x, p.y = 0, W.SPAWN[0], W.SPAWN[1]
    app.state["cell_pick"] = ""
    app.store.save()
    app.bot.game.world = app.store.world
    dom.toast(f"Мир пересоздан (seed {seed})")
    app.render()


def _collect_seeds(app):
    """Считать поля сидов с формы. Пустое/0 — вернуть к выводу из базового."""
    values = {}
    for key in W.SEED_KEYS:
        values[key] = dom.value(f"#seed_{key}", "")
    try:
        app.store.settings["seed"] = int(dom.value("#seedInput", "1337"))
    except ValueError:
        pass
    return app.store.set_seeds(values)


def _seeds_save(app):
    seeds = _collect_seeds(app)
    dom.toast(f"Сиды сохранены ({len(seeds)} шт). Применятся при перегенерации.")
    app.render()


def _seeds_roll(app):
    """Раскатать случайные значения по всем частным сидам."""
    rnd = random.Random()
    app.store.settings["seeds"] = {k: rnd.randrange(1, 2_147_483_647)
                                   for k in W.SEED_KEYS}
    app.store.save()
    dom.toast("Сиды перекатаны — жми «Перегенерировать»")
    app.render()


# ── мировая сетка ───────────────────────────────────────────

def _grid_place(app, arg):
    """Клик по пустой клетке сетки — мастер новой локации на этих координатах."""
    wx, wy = map(int, arg.split(":"))
    app.modal(page.grid_place_form(app, wx, wy))


def _grid_edit(app, arg):
    wx, wy, loc_idx = map(int, arg.split(":"))
    app.modal(page.grid_edit_form(app, wx, wy, loc_idx))


def place_loc(app, loc_idx, wx, wy):
    """Поставить локацию на клетку сетки; занятая — обмен. Пересшивает швы."""
    loc_idx, wx, wy = int(loc_idx), int(wx), int(wy)
    grid = app.store.settings.setdefault("world_grid", {})
    occupant = next((k for k, v in grid.items()
                     if v[0] == wx and v[1] == wy and int(k) != loc_idx), None)
    old = grid.get(str(loc_idx))
    if occupant is not None:
        if old is not None:
            grid[occupant] = old
        else:
            grid.pop(occupant, None)
    grid[str(loc_idx)] = [wx, wy]
    _reseam(app, grid)
    return occupant is not None


def _reseam(app, grid):
    """Снять старые швы и пересшить мир по сетке одной дверью на границу."""
    for c in app.store.world.values():
        if c.link:
            c.link = ()
    W._link_by_grid(app.store.world, grid)
    app.store.save()
    app.bot.game.world = app.store.world


def _grid_shuffle(app):
    grid = app.store.settings.setdefault("world_grid", {})
    if len(grid) <= 1:
        dom.toast("Недостаточно локаций для перемешивания", "err")
        return
    coords = [(x, y) for x in range(10) for y in range(10)]
    random.shuffle(coords)
    for k, (wx, wy) in zip(list(grid.keys()), coords):
        grid[k] = [wx, wy]
    _reseam(app, grid)
    dom.toast(f"Перемешано {len(grid)} локаций, переходы пересшиты")
    app.render()


def _grid_remove(app, loc_idx):
    grid = app.store.settings.setdefault("world_grid", {})
    grid.pop(str(loc_idx), None)
    _reseam(app, grid)
    app.close_modal()
    dom.toast("Локация убрана с сетки")
    app.render()


def _relink(app):
    _reseam(app, app.store.settings.get("world_grid", {}))
    dom.toast("Переходы пересшиты по сетке мира")
    app.render()


# ── локации ─────────────────────────────────────────────────

def _loc_add(app, arg=""):
    """Создать локацию. `arg` = "wx:wy" — координаты клика по сетке."""
    name = dom.value("#loc_name", "").strip()
    if not name:
        dom.toast("Введите название локации!", "err")
        return
    desc = dom.value("#loc_desc", "").strip() or "Новые земли ждут героев."
    ltype = dom.value("#loc_type", "dangerous")
    try:
        lvl = int(dom.value("#loc_level", "1"))
        floors = int(dom.value("#loc_floors", "1"))
        if arg and ":" in arg:
            wx, wy = map(int, arg.split(":"))
        else:
            wx = int(dom.value("#loc_wx", "0"))
            wy = int(dom.value("#loc_wy", "0"))
    except ValueError:
        dom.toast("Уровень, координаты и этажи — числа", "err")
        return
    grid = app.store.settings.setdefault("world_grid", {})
    if (wx, wy) in {tuple(v) for v in grid.values()}:
        dom.toast(f"Клетка [{wx},{wy}] уже занята — выберите другую", "err")
        return
    li, report = app.store.add_location(name, desc, ltype, lvl, wx, wy, floors)
    app.bot.game.world = app.store.world
    app.state["loc"] = li
    app.state["cell_pick"] = ""
    app.close_modal()
    dom.toast(f"Локация «{name}» создана! " + " · ".join(report))
    app.render()


def _loc_save(app, li):
    """Сохранить правки существующей локации."""
    name = dom.value("#loc_name", "").strip()
    if not name:
        dom.toast("Название не может быть пустым", "err")
        return
    msg = app.store.update_location(
        li, name, dom.value("#loc_desc", ""), dom.value("#loc_type", "dangerous"),
        dom.value("#loc_level", "1"), dom.value("#loc_floors", "1"))
    app.bot.game.world = app.store.world
    app.close_modal()
    dom.toast(msg)
    app.render()


def _loc_del(app, li):
    from js import window
    from engine import data as D
    if li >= len(D.LOCATIONS):
        return
    name = D.LOCATIONS[li][0]
    if not window.confirm(f"Удалить локацию «{name}»? Игроки из неё будут "
                          f"перенесены на спавн, мир переиндексируется."):
        return
    msg = app.store.remove_location(li)
    app.bot.game.world = app.store.world
    if app.state.get("loc", 0) >= len(D.LOCATIONS):
        app.state["loc"] = 0
    app.state["cell_pick"] = ""
    dom.toast(msg)
    app.render()
