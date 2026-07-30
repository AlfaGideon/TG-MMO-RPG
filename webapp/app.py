"""Каркас админки: навигация, рендер, подключение обработчиков."""
from engine import permissions
from engine.storage import Store
from webapp import dom, session
from webapp.actions import (audit_actions, bot_actions, content_actions,
                            devops_actions, economy_actions, player_actions,
                            updates_actions, world_actions)
from webapp.backend import LocalStorage
from webapp.pages import audit as page_audit
from webapp.pages import bot as page_bot
from webapp.pages import content as page_content
from webapp.pages import dashboard as page_dash
from webapp.pages import economy as page_economy
from webapp.pages import players as page_players
from webapp.pages import settings as page_settings
from webapp.pages import updates as page_updates
from webapp.pages import world as page_world
from webapp.telegram import TelegramBot

PAGES = [
    ("dash", page_dash), ("bot", page_bot), ("players", page_players),
    ("world", page_world), ("content", page_content),
    ("economy", page_economy), ("audit", page_audit),
    ("settings", page_settings),
    ("updates", page_updates),
]

# Разделы бокового меню: (подпись секции, [ключи страниц])
NAV_SECTIONS = [
    ("", ["dash"]),
    ("Игроки", ["players"]),
    ("Контент мира", ["world", "content", "economy"]),
    ("Система", ["audit", "bot", "settings", "updates"]),
]

# Какое право нужно, чтобы видеть страницу (владелец видит всё).
PAGE_CAPS = {
    "dash": "view_dash", "players": "view_players", "world": "view_world",
    "content": "view_content", "economy": "view_content",
    "bot": "bot_control", "settings": "settings",
    "audit": "",                     # журнал доступен любому админу
    "updates": "manage_content",
}

# cataclysm_actions регистрируется из world_actions — вкладка живёт там же.
ACTION_MODULES = [audit_actions, bot_actions, content_actions,
                  devops_actions, economy_actions, player_actions,
                  updates_actions, world_actions]


class App:
    def __init__(self):
        self.store = Store(LocalStorage())
        content_actions.restore(self.store)
        self.log_lines = []
        self.bot = TelegramBot(self.store, self.log)
        self.actor = None                # None = владелец панели
        self.page = "dash"
        self.state = {"loc": 0, "cell_pick": "", "brush": "grass"}

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
        dom.wire_forms()
        self._paint_status()

    def _nav_markup(self):
        pages = dict(PAGES)
        out = ""
        for label, keys in NAV_SECTIONS:
            keys = [k for k in keys if self.visible(k)]
            if not keys:
                continue
            is_collapsible = bool(label)
            if label:
                out += (f"<div class='nav-section-label' onclick='toggleNavSection(this)' style='cursor:pointer;display:flex;align-items:center;gap:.35rem;user-select:none;transition:opacity .15s;letter-spacing:0.04em;' aria-expanded='true'>"
                        f"<span style='font-size:.65rem;opacity:.5;transform:rotate(90deg);transition:transform .2s;display:inline-block;flex-shrink:0;' aria-hidden='true'>▶</span>"
                        f"<span style='font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;font-weight:600;color:var(--text-muted);'>{label}</span></div>")
            wrapper_class = f"nav-section-group{' nav-section-collapsed' if is_collapsible else ''}"
            out += f"<div class='{wrapper_class}' data-label='{label or ''}'>" if is_collapsible else ""
            for key in keys:
                icon, _, text = pages[key].TITLE.partition(" ")
                active = " active" if key == self.page else ""
                out += (f"<button class='nav-link{active}' data-act='nav' data-arg='{key}'>"
                        f"<span class='nav-icon'>{icon}</span> {text or icon}</button>")
            if is_collapsible:
                out += "</div>"
        out += self._player_ctx_markup()
        if self.actor is not None:
            out += ("<div class='nav-section-label'>Сессия</div>"
                    "<button class='nav-link' data-act='logout'>"
                    "<span class='nav-icon'>🚪</span> Выйти</button>")
        return out

    def _player_ctx_markup(self):
        from webapp.html import esc
        pid = self.state.get("player_ctx")
        if self.page != "players" or not pid:
            return ""
        p = self.store.players.get(int(pid))
        if not p:
            return ""
        return f"""
<div class='nav-section-label'>👤 {esc(p.name)}</div>
<button class='nav-link' data-act='player-edit' data-arg='{p.tg_id}'>✏️ Редактировать</button>
<button class='nav-link' data-act='player-heal' data-arg='{p.tg_id}'>💊 Вылечить</button>
<button class='nav-link' data-act='player-access' data-arg='{p.tg_id}'>🔑 Доступ</button>
"""

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

    def paint_cell(self, key, tile):
        """Мазок кистью по клетке (вызывается из inline JS карты).

        Полный ре-рендер тут недопустим: он сносит сетку из-под курсора и
        рисование обрывается на первой же клетке. Красим точечно — сам
        элемент карты, — а состояние сохраняем в хранилище.
        """
        from engine import data
        c = self.store.world.get(key)
        if c is None:
            return
        if tile in data.TILE_COLORS:
            c.tile = tile
            c.passable = tile != "wall"
        elif tile == "npc":
            c.npc = max(0, c.npc)
        elif tile == "chest":
            c.chest = True
        elif tile == "clear":
            c.mob, c.npc, c.chest = -1, -1, False
        else:
            return
        self.store.save()
        self._repaint_cell(key, c)

    def _repaint_cell(self, key, c):
        """Обновить одну плитку карты без перерисовки страницы."""
        from engine import data
        node = dom.el(f".mapgrid .c[data-key='{key}']")
        if node is None:
            return
        node.style.background = data.TILE_COLORS.get(c.tile, "#333")
        if c.link:
            node.textContent = "🚪"
        elif c.mob >= 0:
            node.textContent = "👾"
        elif c.npc >= 0:
            node.textContent = "💬"
        elif c.chest:
            node.textContent = "📦"
        else:
            node.textContent = ""

    def set_brush(self, brush):
        """Запомнить выбранную кисть, чтобы она пережила ре-рендер."""
        self.state["brush"] = str(brush)

    def pick_brush(self, key):
        """Пипетка: подобрать кисть с клетки (средняя кнопка мыши)."""
        c = self.store.world.get(key)
        if c is None:
            return
        self.state["brush"] = c.tile
        node = dom.el("#paintBrush")
        if node is not None:
            node.value = c.tile
        label = dom.el("#brushLabel")
        if label is not None:
            label.textContent = c.tile
        dom.toast(f"Пипетка: {c.tile}")

    def edit_cell(self, key):
        """Показать клетку в боковом редакторе карты (вызов из inline JS)."""
        from webapp.actions import world_actions
        world_actions._cell_edit(self, key)

    def move_world_loc(self, loc_idx, wx, wy):
        """Переместить локацию на глобальной сетке (drag-and-drop)."""
        from webapp.actions import world_actions
        swapped = world_actions.place_loc(self, loc_idx, wx, wy)
        dom.toast(f"Локация {loc_idx} → [{wx},{wy}]" + (" (обмен)" if swapped else ""))
        self.render()

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
        # Живой таймер для катаклизмов — работает через js.setInterval,
        # а не через встроенные <script>, которые не запускаются в innerHTML.
        try:
            from webapp.live_timer import start_timer, default_cataclysm_formatter, start_clock
            start_timer(interval_ms=1000, selector=".cata-timer[data-until]",
                        formatter=default_cataclysm_formatter)
            # Тематические часы — не мешают интерфейсу, обновляются каждую секунду
            try:
                start_clock(interval_ms=1000, time_id="worldTime", date_id="worldDate")
            except Exception as exc:
                self.log("sys", f"Часы не запущены: {exc}")
        except Exception as exc:
            self.log("sys", f"Таймер не запущен: {exc}")

        token = self.store.settings.get("token", "")
        if token and self.can("bot_control"):
            self.log("sys", "Найден сохранённый токен — пробую автозапуск")
            ok, info = await self.bot.start(token)
            self.log("sys" if ok else "err", f"Автозапуск: {info}")
            self.render()
