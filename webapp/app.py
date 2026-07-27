"""Каркас админки: навигация, рендер, подключение обработчиков."""
from engine.storage import Store
from webapp import dom
from webapp.actions import bot_actions, player_actions, world_actions
from webapp.backend import LocalStorage
from webapp.pages import bot as page_bot
from webapp.pages import content as page_content
from webapp.pages import dashboard as page_dash
from webapp.pages import players as page_players
from webapp.pages import settings as page_settings
from webapp.pages import world as page_world
from webapp.telegram import TelegramBot

PAGES = [
    ("dash", page_dash), ("bot", page_bot), ("players", page_players),
    ("world", page_world), ("content", page_content), ("settings", page_settings),
]

ACTION_MODULES = [bot_actions, player_actions, world_actions]


class App:
    def __init__(self):
        self.store = Store(LocalStorage())
        self.log_lines = []
        self.bot = TelegramBot(self.store, self.log)
        self.page = "dash"
        self.state = {"loc": 0}

    # ── лог ─────────────────────────────────────────────────
    def log(self, level, msg):
        from js import Date
        self.log_lines.append((str(Date.new().toLocaleTimeString()), level, msg))
        self.log_lines = self.log_lines[-400:]
        if self.page == "bot":
            self.render()

    # ── рендер ──────────────────────────────────────────────
    def render(self):
        dom.html("#nav", "".join(
            f"<button class='{'active' if key == self.page else ''}' "
            f"data-act='nav' data-arg='{key}'>{mod.TITLE}</button>"
            for key, mod in PAGES))
        dom.html("#view", dict(PAGES)[self.page].render(self))
        self._paint_status()

    def _paint_status(self):
        dot, txt = dom.el("#botDot"), dom.el("#botText")
        if dot is None or txt is None:
            return
        dot.className = "dot on" if self.bot.running else "dot"
        who = f" @{self.bot.me['username']}" if self.bot.me else ""
        txt.textContent = f"Бот работает{who}" if self.bot.running else "Бот остановлен"

    def modal(self, markup):
        dom.html("#modalBox", markup)
        dom.el("#modal").classList.add("open")

    def close_modal(self, *_):
        dom.el("#modal").classList.remove("open")

    def go(self, key):
        self.page = key or "dash"
        self.render()

    # ── запуск ──────────────────────────────────────────────
    def wire(self):
        dom.register("nav", self.go)
        dom.register("modal-close", self.close_modal)
        for mod in ACTION_MODULES:
            mod.register(self, dom.register)
        dom.bind_actions()

    async def boot(self):
        self.wire()
        self.render()
        self.log("sys", f"Панель загружена · клеток мира: {len(self.store.world)}")
        token = self.store.settings.get("token", "")
        if token:
            self.log("sys", "Найден сохранённый токен — пробую автозапуск")
            ok, info = await self.bot.start(token)
            self.log("sys" if ok else "err", f"Автозапуск: {info}")
            self.render()
