"""Задания серверного стека: выдача, прогресс и сдача.

Долг реестра паритета: модели `Quest` и `CharacterQuest` существовали, в
сиде лежали три задания (`core/seed.py`), но **выдачи и сдачи в боте не
было** — игрок не мог взять ни одного. Браузерный стек умеет задания
давно (`engine/quests.py`).

Здесь только правила; экраны — в `bot/handlers/quests.py`.

Как считается прогресс:
  * `kill`    — счётчик растёт в бою (`bot/handlers/battle._finish_victory`)
                при совпадении имени убитой твари с `objective_target`;
  * `collect` — прогресс не хранится, а считается по сумке в момент показа:
                предметы могли появиться до взятия задания, и требовать
                «собрать заново» было бы нечестно;
  * прочие типы пока засчитываются вручную сдачей — заглушек не делаем.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from core.enums import QuestStatus
from core.models import (Character, CharacterQuest, InventoryItem, Item,
                         Quest)


async def available_for(session, character: Character) -> list[Quest]:
    """Задания, которые герой может взять прямо сейчас."""
    taken = select(CharacterQuest.quest_id).where(
        CharacterQuest.character_id == character.id)
    result = await session.execute(
        select(Quest)
        .where(Quest.min_level <= (character.level or 1))
        .where(Quest.id.not_in(taken))
        .order_by(Quest.min_level, Quest.id)
    )
    return result.scalars().all()


async def active_for(session, character: Character) -> list[CharacterQuest]:
    """Взятые и ещё не сданные задания."""
    result = await session.execute(
        select(CharacterQuest)
        .where(CharacterQuest.character_id == character.id)
        .where(CharacterQuest.status == QuestStatus.ACTIVE)
        .options(selectinload(CharacterQuest.quest))
        .order_by(CharacterQuest.id)
    )
    return result.scalars().all()


async def accept(session, character: Character, quest_id: int) -> dict:
    """Взять задание."""
    quest = await session.get(Quest, quest_id)
    if quest is None:
        return {"ok": False, "reason": "Такого задания больше нет."}
    if (character.level or 1) < (quest.min_level or 1):
        return {"ok": False,
                "reason": f"Нужен {quest.min_level} уровень для этого дела."}

    exists = await session.scalar(
        select(func.count(CharacterQuest.id))
        .where(CharacterQuest.character_id == character.id)
        .where(CharacterQuest.quest_id == quest_id)
    )
    if exists:
        return {"ok": False, "reason": "Ты уже брал это задание."}

    session.add(CharacterQuest(
        character_id=character.id, quest_id=quest_id,
        status=QuestStatus.ACTIVE, progress=0,
    ))
    await session.flush()
    return {"ok": True, "quest": quest}


async def _collected(session, character: Character, target: str) -> int:
    """Сколько предметов с таким именем лежит в сумке."""
    if not target:
        return 0
    total = await session.scalar(
        select(func.coalesce(func.sum(InventoryItem.quantity), 0))
        .join(Item, Item.id == InventoryItem.item_id)
        .where(InventoryItem.character_id == character.id)
        .where(Item.name == target)
    )
    return int(total or 0)


async def progress_of(session, character: Character, cq: CharacterQuest) -> int:
    """Текущий прогресс задания (для `collect` — по содержимому сумки)."""
    quest = cq.quest
    if quest is None:
        return 0
    if quest.objective_type == "collect":
        return await _collected(session, character, quest.objective_target)
    return int(cq.progress or 0)


async def is_complete(session, character: Character, cq: CharacterQuest) -> bool:
    quest = cq.quest
    if quest is None:
        return False
    need = max(1, quest.objective_count or 1)
    return await progress_of(session, character, cq) >= need


async def record_kill(session, character: Character, mob_name: str) -> list[str]:
    """Отметить убийство в активных заданиях. Возвращает строки для экрана.

    Раньше не вызывалось ниоткуда: прогресс заданий не двигался вообще.
    Теперь зовётся из `bot/handlers/battle._finish_victory`.
    """
    if not mob_name:
        return []
    lines = []
    for cq in await active_for(session, character):
        quest = cq.quest
        if quest is None or quest.objective_type != "kill":
            continue
        if (quest.objective_target or "").lower() != mob_name.lower():
            continue
        need = max(1, quest.objective_count or 1)
        cq.progress = min(need, int(cq.progress or 0) + 1)
        if cq.progress >= need:
            lines.append(f"📜 «{quest.name}» — можно сдавать!")
        else:
            lines.append(f"📜 «{quest.name}»: {cq.progress}/{need}")
    if lines:
        await session.flush()
    return lines


async def turn_in(session, character: Character, cq_id: int) -> dict:
    """Сдать выполненное задание и получить награду."""
    from engine.currency import add_currency

    cq = await session.get(CharacterQuest, cq_id)
    if cq is None or cq.character_id != character.id:
        return {"ok": False, "reason": "Это не твоё задание."}
    if cq.status != QuestStatus.ACTIVE:
        return {"ok": False, "reason": "Задание уже закрыто."}

    # Подгружаем сам квест: без него ни проверить, ни наградить.
    result = await session.execute(
        select(CharacterQuest)
        .where(CharacterQuest.id == cq_id)
        .options(selectinload(CharacterQuest.quest))
    )
    cq = result.scalar_one()
    quest = cq.quest
    if quest is None:
        return {"ok": False, "reason": "Задание потерялось."}

    if not await is_complete(session, character, cq):
        need = max(1, quest.objective_count or 1)
        have = await progress_of(session, character, cq)
        return {"ok": False, "reason": f"Ещё не готово: {have}/{need}."}

    # Предметы-цели уходят заказчику, иначе одну связку трав можно было бы
    # сдать во все задания разом.
    taken_note = ""
    if quest.objective_type == "collect":
        left = max(1, quest.objective_count or 1)
        rows = (await session.execute(
            select(InventoryItem)
            .join(Item, Item.id == InventoryItem.item_id)
            .where(InventoryItem.character_id == character.id)
            .where(Item.name == quest.objective_target)
            .where(InventoryItem.is_equipped == False)  # noqa: E712
        )).scalars().all()
        for row in rows:
            if left <= 0:
                break
            take = min(left, row.quantity or 1)
            row.quantity = (row.quantity or 1) - take
            left -= take
            if (row.quantity or 0) <= 0:
                await session.delete(row)
        taken_note = f"\nОтдано: {quest.objective_target} ×{quest.objective_count}"

    add_currency(character, bronze=quest.reward_gold or 0)
    character.experience = (character.experience or 0) + (quest.reward_exp or 0)

    reward_item = None
    if quest.reward_item_id:
        reward_item = await session.get(Item, quest.reward_item_id)
        if reward_item is not None:
            session.add(InventoryItem(
                character_id=character.id, item_id=reward_item.id, quantity=1))

    cq.status = QuestStatus.COMPLETED
    cq.completed_at = func.now()
    await session.flush()

    return {
        "ok": True,
        "name": quest.name,
        "gold": quest.reward_gold or 0,
        "exp": quest.reward_exp or 0,
        "item": reward_item.name if reward_item is not None else "",
        "note": taken_note,
    }
