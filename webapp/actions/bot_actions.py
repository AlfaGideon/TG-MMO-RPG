"""Действия вкладки «Бот»: запуск, транспорт, рассылка."""
from webapp import dom


def register(app, A):
    A("bot-start", lambda _="": _start(app))
    A("bot-stop", lambda _="": _stop(app))
    A("bot-check", lambda _="": _check(app))
    A("token-eye", lambda _="": _eye())
    A("token-forget", lambda _="": _forget(app))
    A("broadcast", lambda _="": _broadcast(app))
    A("log-clear", lambda _="": _log_clear(app))
    A("proxy-save", lambda _="": _proxy_save(app))
    A("git-update", lambda _="": _git_update(app))


async def _start(app):
    token = dom.value("#tokenInput").strip()
    if not token:
        dom.toast("Введи токен", "err")
        return
    ok, info = await app.bot.start(token)
    dom.toast(f"Бот @{info} запущен" if ok else info, "ok" if ok else "err")
    app.render()


def _stop(app):
    app.bot.stop()
    dom.toast("Бот остановлен")
    app.render()


async def _check(app):
    token = dom.value("#tokenInput").strip()
    if not token:
        dom.toast("Введи токен", "err")
        return
    app.bot.token = token
    res = await app.bot.call("getMe")
    if res.get("ok"):
        u = res["result"]
        dom.toast(f"OK: @{u['username']}")
        app.log("sys", f"Токен валиден: @{u['username']} ({u['first_name']})")
    else:
        why = res.get("description", "неизвестная ошибка")
        dom.toast(why[:70], "err")
        if res.get("network"):
            app.log("err", "Похоже, Telegram блокирует браузер — включи прокси в «Транспорт».")


def _eye():
    node = dom.el("#tokenInput")
    if node is not None:
        node.type = "text" if node.type == "password" else "password"


def _forget(app):
    app.store.settings["token"] = ""
    app.store.save()
    dom.set_value("#tokenInput", "")
    dom.toast("Токен удалён")
    app.render()


async def _broadcast(app):
    text = dom.value("#castText").strip()
    if not text:
        dom.toast("Пустое сообщение", "err")
        return
    if not app.bot.running:
        dom.toast("Сначала запусти бота", "err")
        return
    n = await app.bot.broadcast(text)
    dom.toast(f"Отправлено: {n}")


def _log_clear(app):
    app.log_lines = []
    app.render()


def _proxy_save(app):
    app.store.settings["proxy_mode"] = dom.value("#proxyMode", "direct")
    app.store.settings["proxy_url"] = dom.value("#proxyUrl", "").strip()
    app.store.save()
    app.log("sys", f"Транспорт переключён: {app.store.settings['proxy_mode']}")
    dom.toast("Транспорт применён")
    app.render()


def _git_update(app):
    """Перезагружает страницу мимо кеша, чтобы подтянуть свежий код с GitHub."""
    from js import Date, location
    dom.toast("Обновляю интерфейс с GitHub…", "sys")
    try:
        base = str(location.origin) + str(location.pathname)
        location.replace(base + "?v=" + str(int(Date.now())))
    except Exception:
        location.reload()
