"""Действия настроек панели: экспорт, сброс, параметры игры, адрес панели."""
from webapp import dom

DEFAULTS = {"token": "", "seed": 1337, "welcome_bonus": 50,
            "proxy_mode": "direct", "proxy_url": ""}


def register(app, A):
    A("data-export", lambda _="": _export(app))
    A("data-reset", lambda _="": _reset(app))
    A("settings-save", lambda _="": _settings_save(app))
    A("panel-url-save", lambda _="": _panel_url_save(app))


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
    from engine.permissions import normalize_url

    url = normalize_url(dom.value("#panelUrl", ""))
    app.store.settings["panel_url"] = url
    app.store.save()
    dom.toast("Адрес панели сохранён" if url else "Адрес панели очищен")
    app.render()
