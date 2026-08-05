"""Логика заданий: прогресс, проверка условий и награды.

Три вида заданий:
  hunt    — убить тварей вида (прогресс в бою);
  reach   — дойти до локации (прогресс при входе);
  deliver — принести предмет (проверка инвентаря).
"""
import datetime
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload
from core.models import Quest, CharacterQuest, InventoryItem, Character
from core.enums import QuestStatus


async def available_quests(session, character, npc_name=None):
    """Список заданий, которые герой может взять у этого NPC."""
    # Учитываем минимальный уровень и то, что задание ещё не взято (или выполнено сегодня для ежедневных)
    # Сначала находим все взятые активные задания
    taken_ids = (await session.execute(
        select(CharacterQuest.quest_id)
        .where(CharacterQuest.character_id == character.id)
        .where(CharacterQuest.status == QuestStatus.ACTIVE)
    )).scalars().all()
    
    # И находим выполненные сегодня ежедневные
    today = datetime.date.today()
    done_today = (await session.execute(
        select(CharacterQuest.quest_id)
        .where(CharacterQuest.character_id == character.id)
        .where(CharacterQuest.status == QuestStatus.COMPLETED)
        .where(func.date(CharacterQuest.completed_at) == today)
    )).scalars().all()
    
    exclude = set(taken_ids) | set(done_today)
    
    query = select(Quest).where(Quest.min_level <= character.level)
    if npc_name:
        query = query.where(Quest.npc_name == npc_name)
    
    all_q = (await session.execute(query)).scalars().all()
    return [q for q in all_q if q.id not in exclude]


async def active_quests(session, character):
    """Взятые и ещё не выполненные задания."""
    result = await session.execute(
        select(CharacterQuest)
        .options(selectinload(CharacterQuest.quest))
        .where(CharacterQuest.character_id == character.id)
        .where(CharacterQuest.status == QuestStatus.ACTIVE)
    )
    return result.scalars().all()


async def take_quest(session, character, quest_id):
    """Принять задание."""
    quest = await session.get(Quest, quest_id)
    if not quest:
        return False, "Задание не найдено."
    
    # Проверка на повторное взятие
    existing = await session.execute(
        select(CharacterQuest)
        .where(CharacterQuest.character_id == character.id)
        .where(CharacterQuest.quest_id == quest_id)
        .where(CharacterQuest.status == QuestStatus.ACTIVE)
    )
    if existing.scalar_one_or_none():
        return False, "Задание уже принято."
    
    cq = CharacterQuest(
        character_id=character.id,
        quest_id=quest_id,
        status=QuestStatus.ACTIVE,
        progress=0
    )
    session.add(cq)
    
    # Если это reach-квест и мы уже были в этой локации - закрываем сразу
    if quest.objective_type == "reach":
        from core.models import VisitedCell
        visited = await session.scalar(
            select(func.count(VisitedCell.id))
            .where(VisitedCell.character_id == character.id)
            .where(VisitedCell.location_id == quest.location_id)
        )
        if visited:
            cq.progress = 1
            
    await session.commit()
    return True, f"Задание «{quest.name}» принято."


async def advance_hunt(session, character, mob_name):
    """Продвинуть охотничьи квесты."""
    active_q = await session.execute(
        select(CharacterQuest)
        .join(Quest)
        .where(CharacterQuest.character_id == character.id)
        .where(CharacterQuest.status == QuestStatus.ACTIVE)
        .where(Quest.objective_type == "kill")
        .where(Quest.objective_target == mob_name)
    )
    for cq in active_q.scalars().all():
        quest = await session.get(Quest, cq.quest_id)
        if cq.progress < quest.objective_count:
            cq.progress += 1
    await session.commit()


async def advance_reach(session, character, location_id):
    """Продвинуть квесты на исследование."""
    active_q = await session.execute(
        select(CharacterQuest)
        .join(Quest)
        .where(CharacterQuest.character_id == character.id)
        .where(CharacterQuest.status == QuestStatus.ACTIVE)
        .where(Quest.objective_type == "reach")
        .where(Quest.location_id == location_id)
    )
    for cq in active_q.scalars().all():
        cq.progress = 1
    await session.commit()


async def check_deliver(session, character, cq):
    """Проверить наличие предметов для квеста."""
    quest = cq.quest
    if quest.objective_type != "collect":
        return cq.progress >= quest.objective_count
    
    # Считаем количество предметов в инвентаре
    from core.models import Item
    item_id = await session.scalar(select(Item.id).where(Item.name == quest.objective_target))
    if not item_id:
        return False
        
    have = await session.scalar(
        select(func.sum(InventoryItem.quantity))
        .where(InventoryItem.character_id == character.id)
        .where(InventoryItem.item_id == item_id)
    )
    cq.progress = int(have or 0)
    return cq.progress >= quest.objective_count


async def complete_quest(session, character, quest_id):
    """Сдать задание и получить награду."""
    result = await session.execute(
        select(CharacterQuest)
        .options(selectinload(CharacterQuest.quest))
        .where(CharacterQuest.character_id == character.id)
        .where(CharacterQuest.quest_id == quest_id)
        .where(CharacterQuest.status == QuestStatus.ACTIVE)
    )
    cq = result.scalar_one_or_none()
    if not cq:
        return False, "Задание не найдено или уже сдано."
    
    quest = cq.quest
    if not await check_deliver(session, character, cq):
        return False, "Задание ещё не выполнено."
    
    # Если это collect-квест, забираем предметы
    if quest.objective_type == "collect":
        from core.models import Item
        item_id = await session.scalar(select(Item.id).where(Item.name == quest.objective_target))
        needed = quest.objective_count
        
        # Удаляем из инвентаря
        inv_items = (await session.execute(
            select(InventoryItem)
            .where(InventoryItem.character_id == character.id)
            .where(InventoryItem.item_id == item_id)
            .order_by(InventoryItem.quantity.asc())
        )).scalars().all()
        
        for inv in inv_items:
            if needed <= 0: break
            take = min(inv.quantity, needed)
            inv.quantity -= take
            needed -= take
            if inv.quantity <= 0:
                await session.delete(inv)
    
    # Выдаем награду
    character.gold += (quest.reward_gold or 0)
    character.experience += (quest.reward_exp or 0)
    
    loot_msg = ""
    if quest.reward_item_id:
        from core.loot import grant_item
        from core.models import Item
        reward_item = await session.get(Item, quest.reward_item_id)
        if reward_item:
            await grant_item(session, character, reward_item, 1, source="quest", source_detail=quest.name)
            loot_msg = f"\n🎁 Получен предмет: <b>{reward_item.name}</b>"
            
    cq.status = QuestStatus.COMPLETED
    cq.completed_at = datetime.datetime.utcnow()
    
    # Фракционная репутация
    from core import factions as core_factions
    core_factions.award(character, "quest_done")
    
    await session.commit()
    return True, f"✅ <b>{quest.name}</b> выполнено!\n💰 +{quest.reward_gold} | ⭐ +{quest.reward_exp}{loot_msg}"
