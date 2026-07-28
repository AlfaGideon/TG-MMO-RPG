"""Экраны админки внутри бота. Только сборка Reply — работу делает adminops."""
import random

from engine import adminops, audit, data, permissions, rules
from engine.models import Reply

PAGE = 6                    # игроков на страницу списка


def sections(p):
    """Кнопки разделов админки — только те, на которые есть права."""
    rows = []
    if permissions.can_any(p, "view_dash", "view_players"):
        rows.append([("📊 Сводка", "adm:stats"), ("👥 Игроки", "adm:players:0")])
    line = []
    if permissions.can(p, "dungeons"):
        line.append(("🕳 Порталы", "adm:portals"))
    if permissions.can(p, "broadcast"):
        line.append(("📣 Рассылка", "adm:cast"))
    if line:
        rows.append(line)
    if permissions.can_any(p, "view_content", "edit_content"):
        rows.append([("📦 Контент", "adm:content")])
    rows.append([("📜 Журнал действий", "adm:audit:0")])
    return rows


def _back(extra=None):
    rows = list(extra or [])
    rows.append([("◀️ Админка", "admin")])
    return rows


def _deny(exc):
    return Reply(alert=str(exc) or "Недостаточно прав")


# ── сводка ──────────────────────────────────────────────────

def stats(p, store):
    if not permissions.can_any(p, "view_dash", "view_players"):
        return Reply(alert="Нет права смотреть сводку.")
    s = store.stats()
    portals = sum(1 for t in adminops.templates(store) if t.get("portal_cell"))
    admins = sum(1 for q in store.players.values() if q.is_web_admin)
    text = (
        "📊 <b>Сводка мира</b>\n\n"
        f"👥 Игроков: <b>{s['players']}</b> · героев: <b>{s['heroes']}</b>\n"
        f"⭐ Средний уровень: <b>{s['avg_level']}</b>\n"
        f"🪙 Золота в мире: <b>{s['gold']}</b>\n"
        f"☠️ Убито мобов: <b>{s['kills']}</b>\n"
        f"🧱 Клеток мира: <b>{s['cells']}</b>\n"
        f"🌀 Открытых порталов: <b>{portals}</b>\n"
        f"👑 Админов: <b>{admins}</b>\n\n"
        f"<i>Данные общие с веб-панелью.</i>")
    return Reply(text=text, keyboard=_back([[("🔄 Обновить", "adm:stats")]]))


# ── игроки ──────────────────────────────────────────────────

def players(p, store, page=0):
    if not permissions.can(p, "view_players"):
        return Reply(alert="Нет права смотреть игроков.")
    ps = sorted(store.players.values(), key=lambda q: (-q.level, q.name))
    page = max(0, int(page or 0))
    total = max(1, (len(ps) + PAGE - 1) // PAGE)
    page = min(page, total - 1)
    chunk = ps[page * PAGE:(page + 1) * PAGE]

    rows = [[(f"{'👑 ' if q.is_web_admin else ''}{q.name} · ур.{q.level}",
              f"adm:p:{q.tg_id}")] for q in chunk]
    nav = []
    if page > 0:
        nav.append(("◀️", f"adm:players:{page - 1}"))
    nav.append((f"{page + 1}/{total}", "adm:noop"))
    if page < total - 1:
        nav.append(("▶️", f"adm:players:{page + 1}"))
    if len(nav) > 1:
        rows.append(nav)

    text = (f"👥 <b>Игроки</b> ({len(ps)})\n\n"
            + ("\n".join(f"• {q.name} — ур. {q.level} · {q.gold}🪙 · "
                         f"{'герой' if q.created_char else 'без героя'}"
                         for q in chunk) or "<i>Пока никого.</i>"))
    return Reply(text=text, keyboard=_back(rows))


def player_card(p, store, tg_id):
    if not permissions.can(p, "view_players"):
        return Reply(alert="Нет права смотреть игроков.")
    q = store.players.get(int(tg_id))
    if not q:
        return Reply(alert="Игрок не найден.")
    s = rules.stats(q)
    where = data.LOCATIONS[q.loc][0] if q.loc < len(data.LOCATIONS) else "—"
    role = permissions.rank_title(q.web_admin_role) if q.is_web_admin else "—"
    text = (
        f"👤 <b>{q.name}</b> <code>#{q.tg_id}</code>\n\n"
        f"Класс: {q.cls or '—'} · ур. <b>{q.level}</b>\n"
        f"❤️ {q.hp}/{s['max_hp']} · 💙 {q.mp}/{s['max_mp']}\n"
        f"🪙 {q.gold} · 🎒 {len(q.inventory)} предм. · ☠️ {q.kills}\n"
        f"📍 {where} [{q.x},{q.y}]\n"
        f"👑 Доступ: {role}")

    rows = []
    line = []
    if permissions.can(p, "heal_players"):
        line.append(("💊 Исцелить", f"adm:heal:{q.tg_id}"))
    if permissions.can(p, "give_items"):
        line.append(("🎁 Предмет", f"adm:gift:{q.tg_id}"))
    if line:
        rows.append(line)
    if permissions.can(p, "edit_players"):
        rows.append([("🪙 +100", f"adm:gold:{q.tg_id}:100"),
                     ("🪙 −100", f"adm:gold:{q.tg_id}:-100")])
        rows.append([("⭐ +1 ур.", f"adm:lvl:{q.tg_id}:1"),
                     ("⭐ −1 ур.", f"adm:lvl:{q.tg_id}:-1")])
        rows.append([("🏠 В деревню", f"adm:tp:{q.tg_id}")])
    if permissions.can(p, "grant_admin"):
        if q.is_web_admin:
            rows.append([("🔑 Новый пароль", f"adm:pass:{q.tg_id}"),
                         ("🚫 Отозвать", f"adm:revoke:{q.tg_id}")])
        else:
            rows.append([("👑 Выдать доступ", f"adm:grant:{q.tg_id}")])
    if permissions.can(p, "del_players"):
        rows.append([("🗑 Удалить игрока", f"adm:del:{q.tg_id}")])
    rows.append([("◀️ К списку", "adm:players:0")])
    return Reply(text=text, keyboard=_back(rows))


def gift_menu(p, store, tg_id):
    if not permissions.can(p, "give_items"):
        return Reply(alert="Нет права выдавать предметы.")
    q = store.players.get(int(tg_id))
    if not q:
        return Reply(alert="Игрок не найден.")
    rows = [[(f"{rules.item(i)['icon']} {rules.item(i)['name']}",
              f"adm:give:{tg_id}:{i}")] for i in range(len(data.ITEMS))]
    rows.append([("◀️ Назад", f"adm:p:{tg_id}")])
    return Reply(text=f"🎁 <b>Выдать предмет</b>\n\nПолучатель: <b>{q.name}</b>",
                 keyboard=rows)


def grant_menu(p, store, tg_id):
    if not permissions.can(p, "grant_admin"):
        return Reply(alert="Нет права выдавать доступ.")
    q = store.players.get(int(tg_id))
    if not q:
        return Reply(alert="Игрок не найден.")
    rows = [[(permissions.rank_title(r), f"adm:rank:{tg_id}:{r}")]
            for r in permissions.RANK_KEYS]
    rows.append([("◀️ Назад", f"adm:p:{tg_id}")])
    return Reply(text=(f"👑 <b>Выдать доступ</b>\n\nИгрок: <b>{q.name}</b>\n\n"
                       "Выбери ранг. Точечные права потом можно донастроить "
                       "галочками в веб-панели."), keyboard=rows)


# ── порталы ─────────────────────────────────────────────────

def portals(p, store):
    if not permissions.can(p, "dungeons"):
        return Reply(alert="Нет права управлять порталами.")
    tpls = adminops.templates(store)
    lines, rows = [], []
    for t in tpls:
        key = t.get("portal_cell")
        if key:
            cl, cx, cy = map(int, key.split(":"))
            where = data.LOCATIONS[cl][0] if cl < len(data.LOCATIONS) else "?"
            lines.append(f"🌀 <b>{t['name']}</b>\n   открыт: {where} [{cx},{cy}]")
            rows.append([(f"❌ Закрыть: {t['name'][:18]}", f"adm:pclose:{t['id']}")])
        else:
            lines.append(f"⚫ <b>{t['name']}</b>\n   закрыт · ур. {t.get('min_level', 1)}+")
            rows.append([(f"🚪 Открыть: {t['name'][:18]}", f"adm:popen:{t['id']}")])
    text = ("🕳 <b>Порталы подземелий</b>\n\n"
            + ("\n\n".join(lines) if lines else "<i>Шаблонов нет.</i>")
            + "\n\n<i>Открытие/закрытие видно и в веб-панели.</i>")
    return Reply(text=text, keyboard=_back(rows))


def pick_cell(store):
    """Случайная пустая проходимая клетка под портал."""
    free = [k for k, c in store.world.items()
            if c.passable and not c.link and c.npc < 0 and c.mob < 0 and not c.chest]
    return random.choice(free) if free else ""


# ── контент и журнал ────────────────────────────────────────

def content(p, store):
    if not permissions.can_any(p, "view_content", "edit_content"):
        return Reply(alert="Нет права смотреть контент.")
    text = (
        "📦 <b>Контент игры</b>\n\n"
        f"👾 Мобов: <b>{len(data.MOBS)}</b>\n"
        f"🗡 Предметов: <b>{len(data.ITEMS)}</b>\n"
        f"💬 NPC: <b>{len(data.NPCS)}</b>\n"
        f"🎭 Классов: <b>{len(data.CLASSES)}</b>\n"
        f"🗺 Локаций: <b>{len(data.LOCATIONS)}</b>\n\n"
        "<i>Правка контента — в веб-панели, вкладка «Контент».</i>")
    return Reply(text=text, keyboard=_back())


def audit_log(p, store, page=0):
    items = audit.entries(store)
    page = max(0, int(page or 0))
    total = max(1, (len(items) + 5 - 1) // 5)
    page = min(page, total - 1)
    chunk = items[page * 5:(page + 1) * 5]
    body = "\n\n".join(audit.line(e) for e in chunk) or "<i>Журнал пуст.</i>"
    rows = []
    nav = []
    if page > 0:
        nav.append(("◀️", f"adm:audit:{page - 1}"))
    nav.append((f"{page + 1}/{total}", "adm:noop"))
    if page < total - 1:
        nav.append(("▶️", f"adm:audit:{page + 1}"))
    if len(nav) > 1:
        rows.append(nav)
    rows.append([("🔄 Обновить", "adm:audit:0")])
    return Reply(text=f"📜 <b>Действия админов</b> ({len(items)})\n\n{body}",
                 keyboard=_back(rows))
