"""Админ-раздел внутри самого бота: свои права и пароль от веб-панели."""
from engine import permissions, texts
from engine.models import Reply


def panel(p):
    if not p.is_web_admin:
        return Reply(alert="У тебя нет доступа к админке.")
    return Reply(text=texts.admin_panel(p), keyboard=[
        [("🔑 Показать пароль", "adminpass")],
        [("◀️ Меню", "menu")],
    ])


def password(p, store):
    if not p.is_web_admin:
        return Reply(alert="У тебя нет доступа к админке.")
    if not p.web_admin_password:
        p.web_admin_password = permissions.new_password()
        store.save_player(p)
    return Reply(text=texts.admin_password(p), keyboard=[
        [("🛠 Мои права", "admin")], [("◀️ Меню", "menu")]])


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
