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


UPDATE_NOTICE = (
    "📖 <b>Хроники изменились...</b>\n\n"
    "Древние силы перекроили Теневые Земли — мир только что обновился.\n"
    "Панель уходит на короткую перезагрузку, чтобы принять изменения.\n\n"
    "<i>Если что-то не ответит с первого раза — повтори действие через пару секунд.</i>"
)


async def _git_update(app):
    """Уведомляет игроков об обновлении, затем перезагружает панель мимо кеша."""
    from js import Date, location, setTimeout
    from pyodide.ffi import create_proxy

    dom.toast("Обновляю с GitHub…", "sys")

    if app.bot.running:
        app.log("sys", "Рассылаю уведомление об обновлении…")
        try:
            sent = await app.bot.broadcast(UPDATE_NOTICE)
            dom.toast(f"Уведомлено игроков: {sent}")
            app.log("sys", f"Уведомление доставлено: {sent}")
        except Exception as e:
            app.log("err", f"Рассылка обновления не удалась: {e}")
    else:
        app.log("sys", "Бот остановлен — уведомление игрокам не отправлено")

    def reload(*_):
        try:
            base = str(location.origin) + str(location.pathname)
            location.replace(base + "?v=" + str(int(Date.now())))
        except Exception:
            location.reload()

    # даём тостам и последним запросам уйти до перезагрузки страницы
    setTimeout(create_proxy(reload), 1500)
