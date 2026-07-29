"""Права доступа к админке: отдельные функции + ранги, как в кланах MMO.

Ранг — это просто пресет набора «капабилити». Любой ранг можно донастроить
галочками: выдать гейм-мастеру рассылку, забрать у модератора удаление и т.д.
"""
import random
import string

# (ключ, подпись, группа)
CAPS = [
    ("view_dash",    "📊 Видеть сводку",            "Просмотр"),
    ("view_players", "👥 Видеть игроков",           "Просмотр"),
    ("view_world",   "🗺 Видеть карту мира",        "Просмотр"),
    ("view_content", "📦 Видеть контент",           "Просмотр"),
    ("edit_players", "✏️ Править статы игроков",    "Игроки"),
    ("heal_players", "💊 Лечить игроков",           "Игроки"),
    ("give_items",   "🎁 Выдавать предметы",        "Игроки"),
    ("del_players",  "🗑 Удалять игроков",          "Игроки"),
    ("edit_world",   "🧱 Править клетки мира",      "Мир"),
    ("regen_world",  "🎲 Пересоздавать мир",        "Мир"),
    ("dungeons",     "🕳 Порталы и подземелья",     "Мир"),
    ("cataclysms",   "🌋 Насылать катаклизмы",      "Мир"),
    ("edit_content", "📝 Править контент игры",     "Контент"),
    ("bot_control",  "🤖 Запуск/остановка бота",    "Система"),
    ("broadcast",    "📣 Рассылка игрокам",         "Система"),
    ("settings",     "⚙️ Настройки, экспорт, сброс", "Система"),
    ("grant_admin",  "👑 Выдавать доступ другим",   "Система"),
]

CAP_KEYS = [k for k, _, _ in CAPS]
CAP_LABELS = {k: lbl for k, lbl, _ in CAPS}
CAP_GROUPS = []
for _k, _lbl, _g in CAPS:
    if _g not in CAP_GROUPS:
        CAP_GROUPS.append(_g)

# Ранги: (подпись, пресет капабилити)
RANKS = {
    "viewer": ("👁 Наблюдатель", [
        "view_dash", "view_players", "view_world", "view_content"]),
    "moderator": ("🛡 Модератор", [
        "view_dash", "view_players", "view_world", "view_content",
        "heal_players", "give_items"]),
    "gamemaster": ("🎲 Гейм-мастер", [
        "view_dash", "view_players", "view_world", "view_content",
        "edit_players", "heal_players", "give_items",
        "edit_world", "dungeons", "cataclysms", "edit_content", "broadcast"]),
    "admin": ("👑 Администратор", list(CAP_KEYS)),
}

RANK_KEYS = ["viewer", "moderator", "gamemaster", "admin"]


def rank_title(rank):
    return RANKS.get(rank, RANKS["viewer"])[0]


def rank_caps(rank):
    """Пресет капабилити ранга."""
    return list(RANKS.get(rank, RANKS["viewer"])[1])


def caps_of(player):
    """Итоговый набор прав игрока: индивидуальный список либо пресет ранга."""
    if not getattr(player, "is_web_admin", False):
        return set()
    custom = getattr(player, "web_admin_caps", None)
    if custom:
        return {c for c in custom if c in CAP_LABELS}
    return set(rank_caps(getattr(player, "web_admin_role", "viewer")))


def can(player, cap):
    return cap in caps_of(player)


def can_any(player, *caps):
    mine = caps_of(player)
    return any(c in mine for c in caps)


def new_password(length=8):
    """Читаемый пароль без похожих символов (0/O, 1/l)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    try:
        import secrets
        pick = secrets.choice
    except Exception:                              # pragma: no cover
        pick = random.choice
    return "".join(pick(alphabet) for _ in range(length))


def summary(player):
    """Короткая сводка прав для показа игроку в боте."""
    mine = caps_of(player)
    if not mine:
        return "—"
    return "\n".join(f"• {CAP_LABELS[k]}" for k in CAP_KEYS if k in mine)


def slug(text):
    """Безопасный ключ из произвольной строки (для id элементов формы)."""
    return "".join(ch if ch in string.ascii_letters + string.digits else "_"
                   for ch in str(text))


def normalize_url(raw):
    """https://host без хвостового слэша. Пустая строка, если ничего не ввели."""
    url = (raw or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def login_url(base, tg_id):
    """Ссылка входа в панель для инлайн-кнопки бота."""
    base = normalize_url(base)
    return f"{base}/admin-login?uid={tg_id}" if base else ""
