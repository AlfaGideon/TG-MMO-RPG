"""Колизей Теней: асинхронные дуэли с тенями других игроков."""
import random
from datetime import datetime, timezone
from sqlalchemy import select
from core.models import Character, CharacterShadow


def _now():
    return datetime.now(timezone.utc)


async def update_character_shadow(session, character: Character):
    """Обновляет слепок тени персонажа для Арены."""
    from engine.stats import calculate_gear_score
    gs = calculate_gear_score(character)
    result = await session.execute(
        select(CharacterShadow).where(CharacterShadow.character_id == character.id)
    )
    shadow = result.scalar_one_or_none()
    if shadow is None:
        shadow = CharacterShadow(
            character_id=character.id,
            name=character.name,
            character_class=str(character.character_class),
            level=character.level,
            gear_score=gs,
            max_hp=character.max_hp or 100,
            damage=max(10, (character.strength or 10) * 2),
            defense=max(5, (character.endurance or 10)),
            faction=character.faction or "guard",
            arena_rating=character.arena_rating or 1000,
        )
        session.add(shadow)
    else:
        shadow.name = character.name
        shadow.character_class = str(character.character_class)
        shadow.level = character.level
        shadow.gear_score = gs
        shadow.max_hp = character.max_hp or 100
        shadow.damage = max(10, (character.strength or 10) * 2)
        shadow.defense = max(5, (character.endurance or 10))
        shadow.faction = character.faction or "guard"
        shadow.arena_rating = character.arena_rating or 1000
    await session.flush()
    return shadow


async def get_shadow_opponents(session, character: Character, limit: int = 4) -> list[CharacterShadow]:
    """Подбор соперников для дуэли близких по рейтингу."""
    result = await session.execute(
        select(CharacterShadow)
        .where(CharacterShadow.character_id != character.id)
        .order_by(CharacterShadow.arena_rating.desc())
        .limit(limit)
    )
    return result.scalars().all()


async def duel_shadow(session, character: Character, shadow: CharacterShadow) -> dict:
    """Асинхронная дуэль против тени игрока."""
    from core.stats import combat_stats, attack_power, damage_reduction
    stats = await combat_stats(session, character)
    char_hp = character.max_hp or 100
    shadow_hp = shadow.max_hp

    rounds = 0
    log = []

    while char_hp > 0 and shadow_hp > 0 and rounds < 15:
        rounds += 1
        # Ход игрока
        dmg_to_shadow = max(5, attack_power(stats, character) + random.randint(-3, 5) - shadow.defense // 2)
        shadow_hp -= dmg_to_shadow
        log.append(f"Раунд {rounds}: Ты нанёс {dmg_to_shadow} урона тени {shadow.name}.")
        if shadow_hp <= 0:
            break

        # Ход тени
        dmg_to_char = max(3, shadow.damage - damage_reduction(stats) + random.randint(-2, 3))
        char_hp -= dmg_to_char
        log.append(f"Раунд {rounds}: Тень {shadow.name} ответила ударом на {dmg_to_char} урона.")

    victory = shadow_hp <= 0
    tokens_gain = 25 if victory else 5
    rating_change = +20 if victory else -10

    character.arena_rating = max(100, (character.arena_rating or 1000) + rating_change)
    character.gladiator_tokens = (character.gladiator_tokens or 0) + tokens_gain

    # Обновляем тень игрока
    await update_character_shadow(session, character)
    await session.flush()

    return {
        "victory": victory,
        "rounds": rounds,
        "tokens": tokens_gain,
        "rating_change": rating_change,
        "new_rating": character.arena_rating,
        "log": log,
    }
