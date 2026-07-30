"""Защищённый карман для серверного стека — паритет с engine/stash.py.

Как в Таркове: сумка теряется при гибели, карман — нет. Карман намеренно
меньше сумки, иначе выбора нет и игрок просто прячет всё.

Отличие от браузерной версии только в хранении: там список индексов в
`Player.stash`, здесь — флаг `InventoryItem.in_stash`. Числа и правила
одинаковые, и настраиваются из админки через таблицу `app_settings`.
"""
from sqlalchemy import select

from core.models import AppSetting, InventoryItem

# Значения по умолчанию. Живые лежат в app_settings и правятся из админки.
SLOTS = 5
VIP_BONUS = 3
LOSS_SHARE = 0.5
VIP_DAYS = 30

# ключ -> (значение по умолчанию, подпись, пояснение)
TUNABLES = {
    "stash_slots": (SLOTS, "🔒 Ячеек в кармане",
                    "сколько вещей переживает гибель у обычного героя"),
    "stash_vip_bonus": (VIP_BONUS, "👑 Прибавка VIP",
                        "на сколько ячеек VIP расширяет карман"),
    "stash_loss_share": (LOSS_SHARE, "💀 Доля потерь сумки",
                         "какая часть сумки выпадает при смерти (0–1)"),
    "vip_days": (VIP_DAYS, "📅 Срок VIP, дней",
                 "на сколько дней выдаётся VIP кнопкой в админке"),
}

# Безопасные типы локаций: только там можно перекладывать вещи.
SAFE_TYPES = ("safe",)


async def tune(session, key):
    """Настройка из БД или значение по умолчанию."""
    default = TUNABLES[key][0]
    result = await session.execute(
        select(AppSetting).where(AppSetting.key == key)
    )
    row = result.scalar_one_or_none()
    if row is None or not str(row.value).strip():
        return default
    try:
        val = float(row.value)
    except (TypeError, ValueError):
        return default
    if key == "stash_loss_share":
        return max(0.0, min(1.0, val))
    return max(0, int(val))


async def set_tunables(session, values):
    """Сохранить настройки. Пустая строка — вернуть значение по умолчанию."""
    for key in TUNABLES:
        if key not in values:
            continue
        raw = values[key]
        result = await session.execute(
            select(AppSetting).where(AppSetting.key == key)
        )
        row = result.scalar_one_or_none()
        if raw is None or str(raw).strip() == "":
            if row is not None:
                await session.delete(row)
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        if key == "stash_loss_share":
            val = max(0.0, min(1.0, val))
        else:
            val = max(0, int(val))
        if row is None:
            session.add(AppSetting(key=key, value=str(val)))
        else:
            row.value = str(val)


def is_vip(character) -> bool:
    from core.vip import is_vip_active
    return bool(is_vip_active(character))


async def capacity(session, character) -> int:
    """Сколько ячеек в кармане у этого героя."""
    base = await tune(session, "stash_slots")
    if is_vip(character):
        base += await tune(session, "stash_vip_bonus")
    return base


async def stashed(session, character):
    """Вещи, лежащие в защищённом кармане."""
    result = await session.execute(
        select(InventoryItem)
        .where(InventoryItem.character_id == character.id)
        .where(InventoryItem.in_stash == True)
    )
    return result.scalars().all()


async def free_slots(session, character) -> int:
    return max(0, await capacity(session, character)
               - len(await stashed(session, character)))


def safe_here(location) -> bool:
    """Можно ли трогать карман: только в безопасных землях."""
    if location is None:
        return False
    kind = getattr(location, "location_type", None)
    value = getattr(kind, "value", kind)
    return value in SAFE_TYPES


async def put(session, character, inv_item) -> tuple:
    """Убрать вещь в карман. Возвращает (успех, сообщение)."""
    if inv_item.in_stash:
        return False, "Эта вещь уже в кармане."
    if await free_slots(session, character) <= 0:
        cap = await capacity(session, character)
        return False, (f"Карман полон: {cap} ячеек. "
                       f"Освободи место или расширь VIP-статусом.")
    inv_item.in_stash = True
    inv_item.is_equipped = False      # спрятанное нельзя носить
    return True, "🔒 Убрано в защищённый карман."


async def take(session, character, inv_item) -> tuple:
    """Достать вещь обратно в сумку."""
    if not inv_item.in_stash:
        return False, "Эта вещь и так в сумке."
    inv_item.in_stash = False
    return True, "🎒 Возвращено в сумку."


async def drop_on_death(session, character, rng=None):
    """Что выпадает из сумки при гибели. Карман и надетое не трогаем."""
    import random

    rng = rng or random
    result = await session.execute(
        select(InventoryItem)
        .where(InventoryItem.character_id == character.id)
        .where(InventoryItem.in_stash == False)
        .where(InventoryItem.is_equipped == False)
    )
    losable = result.scalars().all()
    if not losable:
        return []
    share = await tune(session, "stash_loss_share")
    count = max(1, int(len(losable) * share))
    return rng.sample(losable, min(count, len(losable)))
