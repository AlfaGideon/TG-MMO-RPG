import random
from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from core.database import async_session
from core.models import User, Character, Location, Mob, Battle
from core.enums import LocationType, BattleResult
from bot.keyboards.inline import battle_menu_keyboard, combat_keyboard, main_menu_keyboard, back_to_main_keyboard
from bot.utils.texts import battle_start_text, battle_round_text, victory_text, defeat_text

router = Router()

# In-memory combat state (for production use Redis)
combat_state = {}


@router.callback_query(F.data == "battle_menu")
async def battle_menu(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        result = await session.execute(
            select(Character)
            .where(Character.user_id == user.id)
            .options(selectinload(Character.location))
        )
        character = result.scalar_one_or_none()
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        await callback.message.edit_text(
            f"⚔️ <b>Боевая зона</b>\n\n"
            f"Ты находишься в: {character.location.name}\n"
            f"❤️ HP: {character.current_hp}/{character.max_hp}\n\n"
            f"Выбери действие:",
            reply_markup=battle_menu_keyboard(character.location.location_type),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "search_enemy")
async def search_enemy(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        result = await session.execute(
            select(Character)
            .where(Character.user_id == user.id)
            .options(selectinload(Character.location))
        )
        character = result.scalar_one_or_none()
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        if character.current_hp <= 0:
            await callback.answer("Ты слишком слаб. Отдохни!", show_alert=True)
            return

        result = await session.execute(
            select(Mob)
            .where(Mob.location_id == character.location_id)
            .where(Mob.is_boss == False)
        )
        mobs = result.scalars().all()
        if not mobs:
            await callback.answer("Здесь нет врагов.", show_alert=True)
            return

        mob = random.choice(mobs)
        combat_state[callback.from_user.id] = {
            "mob_id": mob.id,
            "mob_hp": mob.hp,
            "character_hp": character.current_hp,
            "rounds": 0,
            "damage_dealt": 0,
            "damage_taken": 0,
        }

        await callback.message.edit_text(
            battle_start_text(mob),
            reply_markup=combat_keyboard(),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "combat_attack")
async def combat_attack(callback: CallbackQuery):
    state = combat_state.get(callback.from_user.id)
    if not state:
        await callback.answer("Бой не найден.", show_alert=True)
        return

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        result = await session.execute(
            select(Character).where(Character.user_id == user.id)
        )
        character = result.scalar_one_or_none()

        result = await session.execute(select(Mob).where(Mob.id == state["mob_id"]))
        mob = result.scalar_one()

        # Simple damage formula
        char_dmg = max(1, character.strength + random.randint(-2, 4))
        mob_dmg = max(0, mob.damage - character.endurance // 5 + random.randint(-1, 2))

        state["mob_hp"] -= char_dmg
        state["character_hp"] -= mob_dmg
        state["rounds"] += 1
        state["damage_dealt"] += char_dmg
        state["damage_taken"] += mob_dmg

        if state["mob_hp"] <= 0:
            # Victory
            gold = int(mob.gold_reward * random.uniform(0.8, 1.2))
            exp = mob.exp_reward
            character.gold += gold
            character.experience += exp
            character.current_hp = max(1, state["character_hp"])

            # Level up check (simple)
            needed = character.level * 100
            while character.experience >= needed:
                character.experience -= needed
                character.level += 1
                character.max_hp += 10
                character.max_mp += 5
                character.strength += 1
                character.agility += 1
                character.endurance += 1
                needed = character.level * 100

            battle = Battle(
                character_id=character.id,
                mob_id=mob.id,
                result=BattleResult.VICTORY,
                rounds=state["rounds"],
                damage_dealt=state["damage_dealt"],
                damage_taken=state["damage_taken"],
                gold_earned=gold,
                exp_earned=exp,
            )
            session.add(battle)
            await session.commit()
            del combat_state[callback.from_user.id]

            await callback.message.edit_text(
                victory_text(mob, gold, exp),
                reply_markup=main_menu_keyboard(has_character=True),
                parse_mode="HTML",
            )
            return

        if state["character_hp"] <= 0:
            # Defeat
            character.current_hp = 1
            battle = Battle(
                character_id=character.id,
                mob_id=mob.id,
                result=BattleResult.DEFEAT,
                rounds=state["rounds"],
                damage_dealt=state["damage_dealt"],
                damage_taken=state["damage_taken"],
            )
            session.add(battle)
            await session.commit()
            del combat_state[callback.from_user.id]

            await callback.message.edit_text(
                defeat_text(),
                reply_markup=main_menu_keyboard(has_character=True),
                parse_mode="HTML",
            )
            return

        await session.commit()

        await callback.message.edit_text(
            battle_round_text(
                character.name, mob.name, char_dmg, mob_dmg,
                state["character_hp"], state["mob_hp"], character.max_hp
            ),
            reply_markup=combat_keyboard(),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "combat_flee")
async def combat_flee(callback: CallbackQuery):
    state = combat_state.pop(callback.from_user.id, None)
    if state:
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == callback.from_user.id)
            )
            user = result.scalar_one_or_none()
            result = await session.execute(
                select(Character).where(Character.user_id == user.id)
            )
            character = result.scalar_one_or_none()
            character.current_hp = max(1, state["character_hp"])
            await session.commit()

    await callback.message.edit_text(
        "🏃 Ты сбежал с поля боя. Жизнь дороже чести...",
        reply_markup=main_menu_keyboard(has_character=True),
    )


@router.callback_query(F.data == "rest")
async def rest(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        result = await session.execute(
            select(Character).where(Character.user_id == user.id)
        )
        character = result.scalar_one_or_none()
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        heal = character.max_hp // 3
        character.current_hp = min(character.max_hp, character.current_hp + heal)
        mp_restore = character.max_mp // 3
        character.current_mp = min(character.max_mp, character.current_mp + mp_restore)
        await session.commit()

    await callback.message.edit_text(
        f"🏕 <b>Отдых</b>\n\n"
        f"Ты отдохнул у костра.\n"
        f"❤️ +{heal} HP | 💙 +{mp_restore} MP\n\n"
        f"Текущее здоровье: {character.current_hp}/{character.max_hp}",
        reply_markup=main_menu_keyboard(has_character=True),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "boss_fight")
async def boss_fight(callback: CallbackQuery):
    await callback.answer("Боссы появятся в следующем обновлении!", show_alert=True)
