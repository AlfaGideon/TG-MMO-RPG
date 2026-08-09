"""Глобальный Зал Славы (Hall of Legends / Server Firsts)."""
from datetime import datetime, timezone
from sqlalchemy import select
from core.models import Character, ServerRecord


def _now():
    return datetime.now(timezone.utc)


async def record_server_first(session, record_key: str, title: str, character: Character, detail: str = "") -> bool:
    """Фиксирует историческое первопроходство на сервере."""
    existing = await session.scalar(
        select(ServerRecord).where(ServerRecord.record_key == record_key)
    )
    if existing:
        return False

    rec = ServerRecord(
        record_key=record_key,
        title=title,
        holder_character_name=character.name,
        holder_character_id=character.id,
        detail=detail,
    )
    session.add(rec)
    await session.flush()
    return True


async def get_hall_of_legends(session) -> list[ServerRecord]:
    result = await session.execute(
        select(ServerRecord).order_by(ServerRecord.id.desc())
    )
    return result.scalars().all()


def hall_of_legends_text(records: list[ServerRecord]) -> str:
    if not records:
        return (
            "🏆 <b>Глобальный Зал Славы (Server Legends)</b>\n\n"
            "Летопись мира пока пуста. Соверши великий подвиг, чтобы твоё имя навеки вошло в историю!"
        )
    lines = ["🏆 <b>Глобальный Зал Славы Теневых Земель</b>\n"]
    for r in records[:8]:
        date_str = r.achieved_at.strftime("%d.%m.%Y") if r.achieved_at else "—"
        lines.append(f"⭐ <b>{r.title}</b>\n   Первопроходец: <b>{r.holder_character_name}</b> ({date_str})\n")
    return "\n".join(lines)
