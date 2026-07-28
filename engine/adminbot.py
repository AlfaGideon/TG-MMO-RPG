"""Админ-раздел внутри самого бота: те же функции, что и в веб-панели.

Действия выполняются через engine.adminops, поэтому бот и панель работают
с одним состоянием и пишут в общий журнал (engine.audit).
"""
from engine import adminmenu, permissions, texts
from engine.models import Reply


def _keyboard(p, store, first_row):
    """Кнопки админки. Ссылка на панель берётся из настроек (может быть пустой)."""
    rows = [first_row]
    url = permissions.login_url(store.settings.get("panel_url", ""), p.tg_id)
    if url:
        rows.append([("🌐 Открыть панель", {"url": url})])
    rows.append([("◀️ Меню", "menu")])
    return rows


def panel(p, store):
    """Главный экран админки в боте: разделы по правам + доступ."""
    if not p.is_web_admin:
        return Reply(alert="У тебя нет доступа к админке.")
    rows = adminmenu.sections(p)
    rows.append([("🔑 Логин и пароль", "adminpass")])
    url = permissions.login_url(store.settings.get("panel_url", ""), p.tg_id)
    if url:
        rows.append([("🌐 Открыть панель", {"url": url})])
    rows.append([("◀️ Меню", "menu")])
    return Reply(text=texts.admin_panel(p), keyboard=rows)


def password(p, store):
    if not p.is_web_admin:
        return Reply(alert="У тебя нет доступа к админке.")
    if not p.web_admin_password:
        p.web_admin_password = permissions.new_password()
        store.save_player(p)
    return Reply(text=texts.admin_password(p),
                 keyboard=_keyboard(p, store, [("🛠 Админка", "admin")]))


def grant(store, p, rank="viewer", caps=None, reset_password=True):
    """Выдаёт/обновляет доступ. Возвращает текст уведомления для игрока."""
    p.is_web_admin = True
    p.web_admin_role = rank if rank in permissions.RANKS else "viewer"
    p.web_admin_caps = list(caps) if caps else []
    if reset_password or not p.web_admin_password:
        p.web_admin_password = permissions.new_password()
    p.admin_notified = False
    store.save_player(p)
    return texts.admin_granted(p)


def revoke(store, p):
    p.is_web_admin = False
    p.web_admin_caps = []
    p.web_admin_password = ""
    p.admin_notified = False
    store.save_player(p)
    return texts.admin_revoked()
