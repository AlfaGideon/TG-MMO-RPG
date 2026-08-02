"""Летопись уникальных предметов: кто добыл, у кого побывал, за сколько ушёл.

История ведётся только для экземпляров (`ItemInstance`) — у ресурсов и
расходников своего ID нет, а значит и рассказывать про них нечего.
Благодаря истории вещь, купленная на аукционе, приходит к новому
владельцу «не пустой»: видно, из кого её выбили и через сколько рук она
прошла.
"""
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.models import ItemHistory, ItemInstance

# Что именно произошло с предметом
EVENT_LABELS = {
    "created": ("✨", "создан"),
    "looted": ("⚔️", "выбит в бою"),
    "chest": ("📦", "найден в сундуке"),
    "dungeon": ("🕳", "добыт в подземелье"),
    "crafted": ("🔨", "изготовлен"),
    "bought": ("🏪", "куплен в лавке"),
    "listed": ("📢", "выставлен на аукцион"),
    "sold": ("🔁", "продан на аукционе"),
    "unlisted": ("↩️", "снят с аукциона"),
    "expired": ("⌛", "вернулся с аукциона"),
    "upgraded": ("⚡", "заточен"),
    "granted": ("🛠", "выдан администратором"),
    "quest": ("📜", "получен за задание"),
}

# Источник экземпляра -> событие, которым открывается его летопись
SOURCE_EVENTS = {
    "mob": "looted",
    "chest": "chest",
    "dungeon": "dungeon",
    "craft": "crafted",
    "shop": "bought",
    "quest": "quest",
    "admin": "granted",
    "starter": "created",
    "festive": "created",
    "unique": "created",
}


def event_icon(event: str) -> str:
    return EVENT_LABELS.get(str(event), ("•", str(event)))[0]


def event_label(event: str) -> str:
    return EVENT_LABELS.get(str(event), ("•", str(event)))[1]


async def record(
    session,
    instance: ItemInstance,
    event: str,
    character=None,
    detail: str = "",
    price: int = 0,
):
    """Добавляет запись в летопись предмета."""
    if instance is None:
        return None
    row = ItemHistory(
        instance_id=instance.id,
        event=event,
        character_id=getattr(character, "id", None),
        actor_name=(getattr(character, "name", "") or "")[:64],
        detail=detail[:256],
        price=price,
    )
    session.add(row)
    return row


async def record_birth(session, instance: ItemInstance, character=None, detail: str = ""):
    """Первая строка летописи — как предмет появился на свет."""
    event = SOURCE_EVENTS.get(str(instance.source), "created")
    return await record(
        session, instance, event, character,
        detail or (instance.source_detail or ""),
    )


async def load(session, instance_id: int, limit: int = 40):
    result = await session.execute(
        select(ItemHistory)
        .where(ItemHistory.instance_id == instance_id)
        .order_by(ItemHistory.created_at, ItemHistory.id)
        .limit(limit)
    )
    return result.scalars().all()


async def owners(session, instance_id: int) -> list[str]:
    """Имена всех, у кого вещь побывала, по порядку и без повторов подряд."""
    rows = await load(session, instance_id)
    names = []
    for row in rows:
        name = (row.actor_name or "").strip()
        if name and (not names or names[-1] != name):
            names.append(name)
    return names


def format_history(rows, max_lines: int = 8) -> str:
    """История для карточки предмета в боте."""
    if not rows:
        return ""
    shown = rows[-max_lines:]
    lines = []
    if len(rows) > max_lines:
        lines.append(f"<i>…ещё {len(rows) - max_lines} записей</i>")
    for row in shown:
        when = row.created_at.strftime("%d.%m") if row.created_at else ""
        who = f" — {row.actor_name}" if row.actor_name else ""
        price = f" за {row.price}🟤" if row.price else ""
        detail = f" <i>({row.detail})</i>" if row.detail else ""
        lines.append(
            f"{event_icon(row.event)} {when} {event_label(row.event)}{who}{price}{detail}"
        )
    return "\n".join(lines)


async def history_summary(session, instance: ItemInstance) -> str:
    """Короткая сводка: сколько владельцев и сколько сделок."""
    names = await owners(session, instance.id)
    parts = []
    if len(names) > 1:
        parts.append(f"👥 Владельцев: {len(names)}")
    if instance.trade_count:
        parts.append(f"🔁 Сделок: {instance.trade_count}")
    return " | ".join(parts)
