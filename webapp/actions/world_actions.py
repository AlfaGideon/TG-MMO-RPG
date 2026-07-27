"""Действия вкладок «Мир» и «Настройки»."""
import json

from engine import world as W
from webapp import dom
from webapp.pages import world as page

DEFAULTS = {"token": "", "seed": 1337, "welcome_bonus": 50,
            "proxy_mode": "direct", "proxy_url": ""}


def register(app, A):
    A("world-loc", lambda arg: _pick_loc(app, arg))
    A("world-regen", lambda _="": _regen(app))
    A("cell-edit", lambda arg: app.modal(page.cell_form(app, arg)))
    A("cell-save", lambda arg: _cell_save(app, arg))
    A("data-export", lambda _="": _export(app))
    A("data-import", lambda _="": _import(app))
    A("data-reset", lambda _="": _reset(app))
    A("settings-save", lambda _="": _settings_save(app))


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


def _import(app):
    raw = dom.value("#ioBox").strip()
    try:
        json.loads(raw)
    except Exception:
        dom.toast("Невалидный JSON", "err")
        return
    app.store.backend.set("shadowlands", raw)
    app.store.load()
    app.bot.game.world = app.store.world
    app.bot.transport.settings = app.store.settings
    dom.toast("Импортировано")
    app.render()


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
