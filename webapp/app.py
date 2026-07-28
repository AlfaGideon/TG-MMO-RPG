"""Каркас админки: навигация, рендер, подключение обработчиков."""
from engine import permissions
from engine.storage import Store
from webapp import dom, session
from webapp.actions import (audit_actions, bot_actions, content_actions,
                            devops_actions, economy_actions, player_actions,
                            world_actions)
from webapp.backend import LocalStorage
from webapp.pages import audit as page_audit
from webapp.pages import bot as page_bot
from webapp.pages import content as page_content
from webapp.pages import dashboard as page_dash
from webapp.pages import economy as page_economy
from webapp.pages import players as page_players
from webapp.pages import settings as page_settings
from webapp.pages import world as page_world
from webapp.telegram import TelegramBot

PAGES = [
    ("dash", page_dash), ("bot", page_bot), ("players", page_players),
    ("world", page_world), ("content", page_content),
    ("economy", page_economy), ("audit", page_audit),
    ("settings", page_settings),
]

# Разделы бокового меню: (подпись секции, [ключи страниц])
NAV_SECTIONS = [
    ("", ["dash"]),
    ("Игроки", ["players"]),
    ("Контент мира", ["world", "content", "economy"]),
    ("Система", ["audit", "bot", "settings"]),
]

# Какое право нужно, чтобы видеть страницу (владелец видит всё).
PAGE_CAPS = {
    "dash": "view_dash", "players": "view_players", "world": "view_world",
    "content": "view_content", "economy": "view_content",
    "bot": "bot_control", "settings": "settings",
    "audit": "",                     # журнал доступен любому админу
}

ACTION_MODULES = [audit_actions, bot_actions, content_actions,
                  devops_actions, economy_actions, player_actions,
                  world_actions]


class App:
    def __init__(self):
        self.store = Store(LocalStorage())
        content_actions.restore(self.store)
        self.log_lines = []
        self.bot = TelegramBot(self.store, self.log)
        self.actor = None                # None = владелец панели
        self.page = "dash"
        self.state = {"loc": 0}

    # ── права ───────────────────────────────────────────────
    def can(self, cap):
        """Владелец панели может всё; вошедший админ — только своё."""
        return True if self.actor is None else permissions.can(self.actor, cap)

    def visible(self, key):
        cap = PAGE_CAPS.get(key, "")
        return True if not cap else self.can(cap)

    # ── лог ─────────────────────────────────────────────────
    def log(self, level, msg):
        from js import Date
        self.log_lines.append((str(Date.new().toLocaleTimeString()), level, msg))
        self.log_lines = self.log_lines[-400:]
        if self.page == "bot":
            self.render()

    # ── рендер ──────────────────────────────────────────────
    def render(self):
        if not self.visible(self.page):
            self.page = next((k for k, _ in PAGES if self.visible(k)), "audit")
        dom.html("#nav", self._nav_markup())
        page_mod = dict(PAGES)[self.page]
        title = page_mod.TITLE
        node = dom.el("#pageTitle")
        if node is not None:
            node.textContent = title
        dom.html("#breadcrumbs", self._crumbs_markup(page_mod))
        dom.html("#view", page_mod.render(self))
        self._paint_status()

    def _nav_markup(self):
        pages = dict(PAGES)
        out = ""
        for label, keys in NAV_SECTIONS:
            keys = [k for k in keys if self.visible(k)]
            if not keys:
                continue
            if label:
                out += f"<div class='nav-section-label'>{label}</div>"
            for key in keys:
                icon, _, text = pages[key].TITLE.partition(" ")
                active = " active" if key == self.page else ""
                out += (f"<button class='nav-link{active}' data-act='nav' data-arg='{key}'>"
                        f"<span class='nav-icon'>{icon}</span> {text or icon}</button>")
        if self.actor is not None:
            out += ("<div class='nav-section-label'>Сессия</div>"
                    "<button class='nav-link' data-act='logout'>"
                    "<span class='nav-icon'>🚪</span> Выйти</button>")
        return out

    def _crumbs_markup(self, page_mod):
        from webapp.html import esc
        crumbs = getattr(page_mod, "CRUMBS", None)
        if not crumbs:
            return f"<span class='current'>{esc(page_mod.TITLE)}</span>"
        out = "<a href='#' data-act='nav' data-arg='dash'>Dashboard</a><span class='sep'>/</span>"
        for label, key in crumbs[:-1]:
            out += f"<a href='#' data-act='nav' data-arg='{esc(key)}'>{esc(label)}</a><span class='sep'>/</span>"
        out += f"<span class='current'>{esc(crumbs[-1][0])}</span>"
        return out

    def _paint_status(self):
        dot, txt = dom.el("#botDot"), dom.el("#botText")
        if dot is None or txt is None:
            return
        dot.className = "dot on" if self.bot.running else "dot"
        who = f" @{self.bot.me['username']}" if self.bot.me else ""
        txt.textContent = f"Бот работает{who}" if self.bot.running else "Бот остановлен"
        node = dom.el("#whoami")
        if node is not None:
            node.textContent = session.label(self.actor)

    def modal(self, markup):
        dom.html("#modalBox", markup)
        dom.el("#modal").classList.add("open")

    def close_modal(self, *_):
        dom.el("#modal").classList.remove("open")

    def go(self, key):
        key = key or "dash"
        if not self.visible(key):
            dom.toast("Недостаточно прав для этого раздела", "err")
            return
        self.page = key
        self.render()
        node = dom.el("#layout")          # на мобильных закрываем выехавшее меню
        if node is not None:
            node.classList.remove("sidebar-open")

    def logout(self, *_):
        session.logout()
        from js import location
        location.replace("admin-login.html")

    # ── запуск ──────────────────────────────────────────────
    def wire(self):
        dom.register("nav", self.go)
        dom.register("modal-close", self.close_modal)
        dom.register("logout", self.logout)
        for mod in ACTION_MODULES:
            mod.register(self, dom.register)
        dom.bind_actions()

    async def boot(self):
        self.actor = session.load(self.store)
        self.wire()
        self.render()
        who = session.label(self.actor)
        self.log("sys", f"Панель загружена · {who} · клеток мира: {len(self.store.world)}")
        token = self.store.settings.get("token", "")
        if token and self.can("bot_control"):
            self.log("sys", "Найден сохранённый токен — пробую автозапуск")
            ok, info = await self.bot.start(token)
            self.log("sys" if ok else "err", f"Автозапуск: {info}")
            self.render()
