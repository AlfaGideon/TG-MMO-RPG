"""Система кармы и морального пути: Благочестивый vs Осквернитель."""
from core.models import Character

MAX_KARMA = 500
MIN_KARMA = -500


def change_karma(character: Character, delta: int) -> int:
    """Изменить показатель кармы."""
    cur = getattr(character, "karma_score", 0) or 0
    new_val = max(MIN_KARMA, min(MAX_KARMA, cur + delta))
    character.karma_score = new_val
    return new_val


def karma_status(character: Character) -> tuple[str, str, str]:
    """(значок, титул кармы, описание эффекта)."""
    score = getattr(character, "karma_score", 0) or 0
    if score >= 150:
        return "✨", "Благочестивый праведник", "Благословение света: +15% к лечению и защита от фатального удара."
    elif score <= -150:
        return "💀", "Осквернитель могил", "Тёмное клеймо: +20% к урону магии Тьмы, но паладины смотрят волком."
    else:
        return "⚖️", "Нейтральный странник", "Твои дела пока чисты и не отягощены грехом."


async def redeem_karma(session, character: Character, donation_bronze: int = 300) -> dict:
    """Очистить грехи и вернуть карму к нейтралитету у алтаря часовни."""
    from engine.currency import total_in_bronze, deduct_currency
    if total_in_bronze(character) < donation_bronze:
        return {"ok": False, "reason": f"Для покаяния требуется {donation_bronze}🟤 пожертвования."}

    deduct_currency(character, donation_bronze)
    character.karma_score = 0
    await session.flush()
    return {
        "ok": True,
        "title": "🕊 Покаяние и отпущение грехов",
        "desc": "Священный огонь сжёг груз твоих грехов. Твоя карма очищена!",
    }
