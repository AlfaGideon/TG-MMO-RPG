"""
VIP система для Shadow Lands.

Идея: VIP — не pay-to-win, а удобство + ускорение прогресса + косметика.
Три уровня преимуществ реализованы как множители, проверяемые по флагу is_vip.

Активный VIP = is_vip == True и (vip_until is None или в будущем).
"""
from datetime import datetime, timedelta, timezone
from typing import Optional


def _now():
    return datetime.now(timezone.utc)


def _aware(dt):
    """SQLite возвращает naive, Postgres — aware; приводим к aware."""
    return dt if (dt is None or dt.tzinfo) else dt.replace(tzinfo=timezone.utc)


def is_vip_active(char) -> bool:
    if not getattr(char, 'is_vip', False):
        return False
    until = getattr(char, 'vip_until', None)
    if until is None:
        return True
    # поддержка naive / aware
    try:
        return _aware(until) > _now()
    except Exception:
        # Было fail-open (True) — «мусорные» данные давали вечный VIP.
        # Для платной фичи безопаснее fail-closed.
        return False


def vip_tier(char) -> int:
    """В будущем можно расширить до tier из БД. Сейчас 1 = VIP, 0 = нет."""
    return 1 if is_vip_active(char) else 0


def offline_protected(char) -> bool:
    """Игрок вышел в VIP-режим полной неуязвимости."""
    return is_vip_active(char) and bool(getattr(char, "offline_protected", False))


def set_offline(char, enabled: bool) -> bool:
    """Включить/выключить VIP-выход. Возвращает новое состояние."""
    if enabled and not is_vip_active(char):
        raise ValueError("Режим «Я офлайн» доступен только VIP")
    if enabled and getattr(char, "battle", None):
        raise ValueError("Сначала закончи бой")
    char.offline_protected = bool(enabled)
    return char.offline_protected


# ── Модификаторы ──────────────────────────────────────

# Боевые награды
VIP_GOLD_MULT = 1.5
VIP_EXP_MULT = 1.3
VIP_LOOT_QUALITY_BONUS = 10  # +10 к качеству (100 → 110)
VIP_RARE_CHANCE_BONUS = 0.05
VIP_CHEST_GOLD_MULT = 1.5

# Удобство
VIP_FAST_TRAVEL_ANY = True  # может лететь в любую посещённую локацию, не только safe
VIP_AUCTION_FEE_DISCOUNT = 1.0  # 100% скидка на комиссию (если комиссия будет)
VIP_AUCTION_SLOTS_BONUS = 3  # +3 слота к лимиту аукциона
VIP_INVENTORY_BONUS = 20  # условные слоты (для UI, не жёсткий лимит в коде пока)

# Таймеры — VIP живёт быстрее
VIP_RESPAWN_REDUCTION = 0.25  # -25% к ожиданию личного отката? (для будущего)
VIP_CHEST_RESPAWN_REDUCTION = 0.5  # сундуки для VIP восстанавливаются быстрее в личном трекере

# Daily
VIP_DAILY_GOLD = 200
VIP_DAILY_EXP = 100


def apply_vip_gold(base_gold: int, char) -> int:
    if is_vip_active(char):
        return int(base_gold * VIP_GOLD_MULT)
    return base_gold


def apply_vip_exp(base_exp: int, char) -> int:
    if is_vip_active(char):
        return int(base_exp * VIP_EXP_MULT)
    return base_exp


def apply_vip_chest_gold(base_gold: int, char) -> int:
    if is_vip_active(char):
        return int(base_gold * VIP_CHEST_GOLD_MULT)
    return base_gold


def vip_benefits_list() -> list[dict]:
    """Список преимуществ для отображения в админке и в боте."""
    return [
        {"icon": "💰", "title": "Золото +50%", "desc": "Все награды золотом за убийство мобов, боссов и открытие сундуков увеличены на 50%."},
        {"icon": "⭐", "title": "Опыт +30%", "desc": "Прокачка быстрее на 30% — быстрее открываются локации и классы."},
        {"icon": "🎁", "title": "Лут +10% качества", "desc": "Выпадающие предметы получают бонус к качеству и +5% шанс на редкую вещь."},
        {"icon": "📦", "title": "Сундуки +50% золота", "desc": "Золото из сундуков и их личный откат быстрее. VIP видит таймер восстановления."},
        {"icon": "🗺️", "title": "Быстрый полёт везде", "desc": "Обычные игроки могут телепортироваться только в безопасные посещённые локации. VIP — в любую посещённую."},
        {"icon": "⚖️", "title": "Аукцион без комиссии +3 слота", "desc": "Выставление лотов бесплатно, лимит одновременных лотов увеличен."},
        {"icon": "🔥", "title": "Ежедневный бонус", "desc": f"Каждый день {VIP_DAILY_GOLD} золота и {VIP_DAILY_EXP} опыта просто за вход с VIP."},
        {"icon": "👑", "title": "Значок и приоритет", "desc": "VIP-иконка в топах, в профиле, на карте. При техработах — приоритет входа (future)."},
        {"icon": "🏰", "title": "Доступ к VIP-локациям (future)", "desc": "При включении — отдельные локации и квесты только для VIP."},
        {"icon": "💬", "title": "Цветной ник и эмоции", "desc": "Возможность ставить кастомный эмодзи-статус и цвет имени в чате (future)."},
    ]


def vip_status_text(char) -> str:
    if not is_vip_active(char):
        return "❌ VIP не активен"
    until = getattr(char, 'vip_until', None)
    if until:
        return f"👑 VIP до {until.strftime('%Y-%m-%d %H:%M')} UTC"
    return "👑 VIP бессрочно (вечный)"
