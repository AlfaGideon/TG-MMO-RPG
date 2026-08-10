import random

from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core import magic, statpoints
from core.database import async_session
from core.loot import give_mob_loot
from core.models import User, Character, Mob, Battle, Cell, MobSpawn
from core.enums import BattleResult
from core.spawns import kill_spawn, spawn_at_cell
from core.stats import attack_power, combat_stats, damage_reduction
from bot.keyboards.inline import combat_keyboard, combat_stance_keyboard, continue_keyboard
from bot.utils.texts import (
    battle_start_text, battle_round_text, victory_text, defeat_text, loot_text,
)
from bot.utils.photos import send_or_edit_photo
from bot.utils.edit import safe_edit_text

router = Router()


def _mob_image(mob) -> str:
    if (getattr(mob, "image_url", None) or "").strip():
        return mob.image_url
    from core.mob_images import mob_image_url
    return mob_image_url(getattr(mob, "name", ""))


combat_state = {}


async def _load_character(session, telegram_id: int, with_cell: bool = False):
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        return None
    query = select(Character).where(Character.user_id == user.id)
    if with_cell:
        query = query.options(
            selectinload(Character.location),
            selectinload(Character.cell),
        )
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def _lose_bag(session, character):
    """Гибель: золото и часть сумки остаются надгробием, карман цел.

    Паритет с браузерным стеком: вещи не исчезают, а ждут хозяина на месте
    смерти. Дошёл обратно — вернул всё, погиб по дороге — потерял.
    Возвращает строку для экрана поражения.
    """
    from core import death as core_death
    from core import stash as stash_core

    lost = await stash_core.drop_on_death(session, character)
    kept = len(await stash_core.stashed(session, character))
    item_ids = [inv.item_id for inv in lost]
    for inv in lost:
        await session.delete(inv)

    from engine.currency import total_in_bronze, deduct_currency
    total_b = total_in_bronze(character)
    gold_lost = total_b // 5
    deduct_currency(character, gold_lost)
    grave = await core_death.bury(session, character, gold_lost, item_ids)
    core_death.wound(character)

    parts = []
    if grave:
        parts.append(f"🪦 Осталось на месте гибели: <b>{gold_lost}</b> 🟤")
    if lost:
        parts.append(f"🎒 Выпало из сумки: <b>{len(lost)}</b>")
    if kept:
        parts.append(f"🔒 В кармане уцелело: <b>{kept}</b>")
    if grave:
        parts.append("<i>Вернись и забери — если успеешь за сутки.</i>")
    hurt = core_death.note(character)
    if hurt:
        parts.append(hurt)
    return ("\n\n" + "\n".join(parts)) if parts else ""


@router.callback_query(F.data == "battle_menu")
async def battle_menu(callback: CallbackQuery):
    async with async_session() as session:
        character = await _load_character(session, callback.from_user.id, with_cell=True)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        cell = character.cell
        spawn = await spawn_at_cell(session, cell) if cell else None
        if spawn and spawn.mob:
            await start_cell_battle(callback, character, spawn, session)
            return

        await safe_edit_text(
            callback,
            f"⚔️ <b>Боевая зона</b>\n\n"
            f"Ты находишься в: {character.location.name}\n"
            f"❤️ HP: {character.current_hp}/{character.max_hp}\n\n"
            f"Осмотрись на клетке, чтобы найти врагов.",
            reply_markup=continue_keyboard(),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "cell_attack")
async def cell_attack(callback: CallbackQuery):
    async with async_session() as session:
        character = await _load_character(session, callback.from_user.id, with_cell=True)
        if not character or not character.cell:
            await callback.answer("Здесь нет врагов!", show_alert=True)
            return

        spawn = await spawn_at_cell(session, character.cell)
        if not spawn or not spawn.mob:
            await callback.answer("Враг уже ушёл отсюда.", show_alert=True)
            return

        await start_cell_battle(callback, character, spawn, session)


async def start_cell_battle(callback, character, spawn: MobSpawn, session):
    if character.current_hp <= 0:
        await callback.answer("Ты слишком слаб. Отдохни!", show_alert=True)
        return

    mob = spawn.mob
    if spawn.engaged_by_id and spawn.engaged_by_id != character.id:
        await callback.answer("С этим врагом уже кто-то сражается.", show_alert=True)
        return

    from sqlalchemy import or_, update
    claimed = await session.execute(
        update(MobSpawn)
        .where(MobSpawn.id == spawn.id)
        .where(MobSpawn.is_alive == True)  # noqa: E712
        .where(or_(MobSpawn.engaged_by_id.is_(None),
                   MobSpawn.engaged_by_id == character.id))
        .values(engaged_by_id=character.id)
    )
    if claimed.rowcount != 1:
        await callback.answer("С этим врагом уже кто-то сражается.", show_alert=True)
        return
    spawn.engaged_by_id = character.id
    if not spawn.current_hp:
        spawn.current_hp = mob.hp
    await session.commit()

    combat_state[callback.from_user.id] = {
        "spawn_id": spawn.id,
        "mob_id": mob.id,
        "mob_hp": spawn.current_hp,
        "character_hp": character.current_hp,
        "rounds": 0,
        "damage_dealt": 0,
        "damage_taken": 0,
        "stance": "balanced",
        "primer_school": None,
        "statuses": {},
        "channeling": None,
    }

    await send_or_edit_photo(
        callback,
        battle_start_text(mob, spawn.current_hp),
        reply_markup=combat_keyboard(),
        image_url=_mob_image(mob),
    )


async def _finish_victory(callback, session, character, mob, spawn, state):
    """Награда за победу: золото, опыт, уровень и уникальный лут (с VIP бонусами)."""
    from core.vip import apply_vip_gold, apply_vip_exp, is_vip_active
    from core.realtime import publish as rt_publish

    gold_min = mob.gold_min or 0
    gold_max = mob.gold_max or 0
    if gold_max > 0 and gold_max >= gold_min:
        base_gold = random.randint(gold_min, gold_max)
    else:
        base_gold = int(mob.gold_reward * random.uniform(0.8, 1.2))
    base_exp = mob.exp_reward

    from core import factions as core_factions
    my_f = core_factions.allegiance(character)
    decree_b = await core_factions.active_decree_bonuses(session, my_f)
    outpost_b = await core_factions.faction_outpost_bonuses(session, my_f)
    f_gold_mult = decree_b.get("gold_mult", 1.0) * (1.0 + outpost_b.get("gold_pct", 0) / 100.0)
    f_exp_mult = decree_b.get("exp_mult", 1.0) * (1.0 + outpost_b.get("exp_pct", 0) / 100.0)

    gold = int(apply_vip_gold(base_gold, character) * f_gold_mult)
    exp = int(apply_vip_exp(base_exp, character) * f_exp_mult)

    from engine.currency import add_currency
    add_currency(character, bronze=gold)
    character.experience += exp

    # Фракции: за нежить хвалит стража, за зверьё — тоже, но меньше.
    rep_lines = core_factions.award_for_mob(character, mob)

    # Realtime: победа в бою
    try:
        await rt_publish("battle_victory", {
            "character_id": character.id,
            "character_name": character.name,
            "mob_name": mob.name,
            "gold": gold,
            "exp": exp,
            "location_id": character.location_id,
            "is_vip": is_vip_active(character),
        })
    except Exception:
        pass
    character.current_hp = max(1, state["character_hp"])

    # Вместо фиксированного прироста класса уровень даёт очки
    # характеристик — герой сам вкладывает их в профиле (🎯 Очки).
    levels_gained = 0
    points_gained = 0
    needed = character.level * 100
    while character.experience >= needed:
        character.experience -= needed
        character.level += 1
        levels_gained += 1
        points_gained += statpoints.perks_for_level(character.level)
        needed = character.level * 100
    if levels_gained:
        character.stat_points = statpoints.free_points(character) + points_gained
        character.current_hp = character.max_hp
        character.current_mp = character.max_mp

    session.add(Battle(
        character_id=character.id, mob_id=mob.id, result=BattleResult.VICTORY,
        rounds=state["rounds"], damage_dealt=state["damage_dealt"],
        damage_taken=state["damage_taken"], gold_earned=gold, exp_earned=exp,
    ))

    loot = await give_mob_loot(session, character, mob)

    # Моб умирает: место в популяции освобождается, респавн по таймеру
    if spawn:
        await kill_spawn(session, spawn, mob)

    await session.commit()
    combat_state.pop(callback.from_user.id, None)

    text = victory_text(mob, gold, exp)
    if rep_lines:                      # чем поступок отозвался у фракций
        text += "\n\n" + "\n".join(rep_lines)
    if levels_gained:
        text += (f"\n\n🎖 <b>Новый уровень: {character.level}!</b>\nЗдоровье восстановлено.\n"
                 f"🎯 Получено очков характеристик: <b>+{points_gained}</b> "
                 f"(свободно: {statpoints.free_points(character)}).\n"
                 f"<i>Распредели их: 🧙 Профиль → 🎯 Очки характеристик.</i>")
    if loot:
        text += "\n\n" + loot_text(loot)

    await safe_edit_text(
        callback,
        text,
        reply_markup=continue_keyboard(),
        parse_mode="HTML",
    )


async def _finish_defeat(callback, session, character, mob, spawn, state):
    """Поражение в бою: надгробие с частью добра, ранение и сброс моба."""
    character.current_hp = 1
    session.add(Battle(
        character_id=character.id, mob_id=mob.id, result=BattleResult.DEFEAT,
        rounds=state["rounds"], damage_dealt=state["damage_dealt"],
        damage_taken=state["damage_taken"],
    ))
    if spawn is not None:
        spawn.engaged_by_id = None
        # Моб зализывает раны, а не остаётся с 1 HP навсегда
        spawn.current_hp = mob.hp
    note = await _lose_bag(session, character)
    await session.commit()
    combat_state.pop(callback.from_user.id, None)

    await safe_edit_text(
        callback,
        defeat_text() + note,
        reply_markup=continue_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "combat_attack")
async def combat_attack(callback: CallbackQuery):
    state = combat_state.get(callback.from_user.id)
    if not state:
        await callback.answer("Бой не найден.", show_alert=True)
        return

    async with async_session() as session:
        character = await _load_character(session, callback.from_user.id)
        if not character:
            await callback.answer("Персонаж не найден.", show_alert=True)
            return

        result = await session.execute(select(Mob).where(Mob.id == state["mob_id"]))
        mob = result.scalar_one_or_none()
        if mob is None:
            combat_state.pop(callback.from_user.id, None)
            await callback.answer("Противник исчез.", show_alert=True)
            return

        spawn = await session.get(MobSpawn, state["spawn_id"]) if state.get("spawn_id") else None
        if spawn is not None and not spawn.is_alive:
            combat_state.pop(callback.from_user.id, None)
            await callback.answer("Этого врага уже добили.", show_alert=True)
            return

        stats = await combat_stats(session, character)
        stance = state.get("stance", "balanced")
        statuses = state.setdefault("statuses", {})

        # Эффект стойки
        stance_dmg_mult = 1.30 if stance == "berserk" else 1.0
        stance_def_mult = 0.80 if stance == "berserk" else (1.25 if stance == "parry" else 1.0)
        if stance == "focus":
            mp_regen = max(2, (character.max_mp or 50) // 10)
            character.current_mp = min(character.max_mp or 50, (character.current_mp or 0) + mp_regen)

        # Расколотая броня от элементальных реакций
        mob_def = (mob.defense or 0)
        if "broken_armor" in statuses:
            mob_def = mob_def // 2

        # Урон игрока: статы + оружие, минус защита моба
        base_atk = attack_power(stats, character) + random.randint(-2, 4) - mob_def // 2
        char_dmg = max(1, int(base_atk * stance_dmg_mult))
        crit = random.random() < min(0.35, (stats.get("luck", 10)) * 0.008)
        if crit:
            char_dmg = int(char_dmg * 1.7)

        # Обработка входящего урона (или оглушения)
        is_stunned = "stun" in statuses
        counter_dmg = 0
        if is_stunned:
            mob_dmg = 0
            del statuses["stun"]
        elif state.get("channeling"):
            # Враг завершил подготовку заклинания!
            chan = state.pop("channeling")
            mob_dmg = max(5, int(chan["damage"] - damage_reduction(stats) * stance_def_mult))
        else:
            base_mob_dmg = mob.damage - damage_reduction(stats) * stance_def_mult + random.randint(-1, 2)
            mob_dmg = max(0, int(base_mob_dmg * (1.20 if stance == "berserk" else 1.0)))
            # Парирование и контратака
            if stance == "parry" and mob_dmg > 0 and random.random() < 0.35:
                counter_dmg = max(2, char_dmg // 2)
                char_dmg += counter_dmg
                mob_dmg = mob_dmg // 2

        # Тики периодического урона (горение / кровотечение)
        dot_dmg = 0
        if "burn" in statuses:
            dot_dmg += max(3, int(mob.hp * 0.08))
            statuses["burn"] -= 1
            if statuses["burn"] <= 0:
                del statuses["burn"]

        state["mob_hp"] -= (char_dmg + dot_dmg)
        state["character_hp"] -= mob_dmg
        state["rounds"] += 1
        state["damage_dealt"] += (char_dmg + dot_dmg)
        state["damage_taken"] += mob_dmg

        # Шанс моба начать подготовку сильного удара на следующем ходе
        if not state.get("channeling") and state["rounds"] % 3 == 0 and state["mob_hp"] > 0 and random.random() < 0.45:
            state["channeling"] = {"name": f"🔥 Разрушительный выпад {mob.name}", "damage": int(mob.damage * 2.2)}

        if spawn is not None:
            spawn.current_hp = max(0, state["mob_hp"])

        if state["mob_hp"] <= 0:
            await _finish_victory(callback, session, character, mob, spawn, state)
            return

        if state["character_hp"] <= 0:
            await _finish_defeat(callback, session, character, mob, spawn, state)
            return

        await session.commit()

        extra_notes = []
        if counter_dmg:
            extra_notes.append(f"🛡 <b>Парирование!</b> Контратака на +{counter_dmg} урона!")
        if is_stunned:
            extra_notes.append("💫 <i>Враг оглушён и пропускает ход!</i>")
        if dot_dmg:
            extra_notes.append(f"🔥 <i>Периодический урон стихий: +{dot_dmg}</i>")
        if state.get("channeling"):
            extra_notes.append(f"⚠️ <b>ВНИМАНИЕ: {mob.name} готовит {state['channeling']['name']}! Прерви каст!</b>")

        round_txt = battle_round_text(
            character.name, mob.name, char_dmg, mob_dmg,
            state["character_hp"], state["mob_hp"], character.max_hp,
            crit=crit,
        )
        if extra_notes:
            round_txt += "\n\n" + "\n".join(extra_notes)

        await send_or_edit_photo(
            callback,
            round_txt,
            reply_markup=combat_keyboard(is_channeling=bool(state.get("channeling")), stance=stance),
            image_url=_mob_image(mob),
        )


@router.callback_query(F.data == "combat_defend")
async def combat_defend(callback: CallbackQuery):
    """Защита: пропускаешь удар, но получаешь вдвое меньше урона."""
    state = combat_state.get(callback.from_user.id)
    if not state:
        await callback.answer("Бой не найден.", show_alert=True)
        return

    async with async_session() as session:
        character = await _load_character(session, callback.from_user.id)
        result = await session.execute(select(Mob).where(Mob.id == state["mob_id"]))
        mob = result.scalar_one_or_none()
        if not character or mob is None:
            await callback.answer("Бой прерван.", show_alert=True)
            return

        spawn = await session.get(MobSpawn, state["spawn_id"]) if state.get("spawn_id") else None

        stats = await combat_stats(session, character)
        stance = state.get("stance", "balanced")
        mob_dmg = max(0, (mob.damage - damage_reduction(stats)) // 2)
        state["character_hp"] -= mob_dmg
        state["rounds"] += 1
        state["damage_taken"] += mob_dmg

        # В глухой обороне понемногу восстанавливается дыхание
        max_hp_val = character.max_hp or 100
        heal = max(1, max_hp_val // 40)
        state["character_hp"] = min(max_hp_val, state["character_hp"] + heal)

        if state["character_hp"] <= 0:
            await _finish_defeat(callback, session, character, mob, spawn, state)
            return

        await session.commit()

    await send_or_edit_photo(
        callback,
        f"🛡 <b>Ты уходишь в защиту</b>\n\n"
        f"{mob.name} бьёт, но щит держит: всего {mob_dmg} урона.\n"
        f"Ты переводишь дыхание: +{heal} HP.\n\n"
        f"❤️ Ты: {state['character_hp']}/{character.max_hp}\n"
        f"👾 {mob.name}: {state['mob_hp']}",
        reply_markup=combat_keyboard(is_channeling=bool(state.get("channeling")), stance=stance),
        image_url=_mob_image(mob),
    )


@router.callback_query(F.data == "combat_skill")
async def combat_skill(callback: CallbackQuery):
    """Умение: заклинание или сильный удар с элементальными комбо-реакциями."""
    state = combat_state.get(callback.from_user.id)
    if not state:
        await callback.answer("Бой не найден.", show_alert=True)
        return

    async with async_session() as session:
        character = await _load_character(session, callback.from_user.id)
        result = await session.execute(select(Mob).where(Mob.id == state["mob_id"]))
        mob = result.scalar_one_or_none()
        if not character or mob is None:
            await callback.answer("Бой прерван.", show_alert=True)
            return

        cost = max(5, (character.max_mp or 50) // 8)
        if (character.current_mp or 0) < cost:
            await callback.answer(f"Не хватает маны (нужно {cost}).", show_alert=True)
            return

        stats = await combat_stats(session, character)
        character.current_mp = max(0, (character.current_mp or cost) - cost)
        stance = state.get("stance", "balanced")
        statuses = state.setdefault("statuses", {})

        # Магический дар и элементальные реакции
        affinities = await magic.get_affinities(session, character.id)
        school_bonus = magic.spell_bonus(affinities, stats["intelligence"])
        best = magic.best_affinity(affinities)

        # Фокус нужной школы в руках
        focus_bonus = 0
        if best is not None:
            for inv in stats.get("gear", []):
                inst = inv.instance if inv.instance_id else None
                if inst is not None and inst.magic_school == best.school:
                    focus_bonus += inst.magic_power or 0

        stance_spell_mult = 1.25 if stance == "focus" else (1.30 if stance == "berserk" else 1.0)
        base_char_dmg = int(attack_power(stats, character) * 1.8) + stats["intelligence"] // 2 + school_bonus + focus_bonus
        char_dmg = max(2, int(base_char_dmg * stance_spell_mult))

        # Проверка элементарной реакции (комбо со стихией предыдущего каста)
        reaction_note = ""
        if best is not None:
            reaction = magic.trigger_elemental_reaction(state.get("primer_school"), best.school)
            if reaction:
                char_dmg = int(char_dmg * reaction["mult"])
                reaction_note = f"\n💥 <b>{reaction['name']}!</b> {reaction['desc']}"
                if reaction["effect"] in ("burn", "broken_armor", "stun"):
                    statuses[reaction["effect"]] = 2
            state["primer_school"] = best.school

        mob_dmg = max(0, mob.damage - damage_reduction(stats) + random.randint(-1, 2))

        state["mob_hp"] -= char_dmg
        state["character_hp"] -= mob_dmg
        state["rounds"] += 1
        state["damage_dealt"] += char_dmg
        state["damage_taken"] += mob_dmg

        spawn = await session.get(MobSpawn, state["spawn_id"]) if state.get("spawn_id") else None
        if spawn is not None:
            spawn.current_hp = max(0, state["mob_hp"])

        if state["mob_hp"] <= 0:
            await _finish_victory(callback, session, character, mob, spawn, state)
            return

        if state["character_hp"] <= 0:
            await _finish_defeat(callback, session, character, mob, spawn, state)
            return

        await session.commit()

    if best is not None:
        head = (
            f"{magic.school_icon(best.school)} <b>"
            f"{magic.school_name(best.school)}!</b> (−{cost} MP)"
        )
    else:
        head = f"✨ <b>Удар силой!</b> (−{cost} MP)"

    await send_or_edit_photo(
        callback,
        f"{head}\n\n"
        f"Ты вкладываешься полностью: {char_dmg} урона!{reaction_note}\n"
        f"{mob.name} отвечает {mob_dmg} урона.\n\n"
        f"❤️ Ты: {state['character_hp']}/{character.max_hp}\n"
        f"💙 MP: {character.current_mp}/{character.max_mp}\n"
        f"👾 {mob.name}: {state['mob_hp']}",
        reply_markup=combat_keyboard(is_channeling=bool(state.get("channeling")), stance=stance),
        image_url=_mob_image(mob),
    )


@router.callback_query(F.data == "combat_interrupt")
async def combat_interrupt(callback: CallbackQuery):
    """Прерывание смертоносного заклинания врага щитом/ударом."""
    state = combat_state.get(callback.from_user.id)
    if not state or not state.get("channeling"):
        await callback.answer("Враг сейчас ничего не готовит.", show_alert=True)
        return

    async with async_session() as session:
        character = await _load_character(session, callback.from_user.id)
        result = await session.execute(select(Mob).where(Mob.id == state["mob_id"]))
        mob = result.scalar_one_or_none()
        if not character or not mob:
            await callback.answer("Бой прерван.", show_alert=True)
            return

        # Прерывание сбивает каст и оглушает моба!
        chan_name = state["channeling"]["name"]
        state["channeling"] = None
        state.setdefault("statuses", {})["stun"] = 1
        bash_dmg = max(5, (character.strength or 10) // 2)
        state["mob_hp"] -= bash_dmg

        spawn = await session.get(MobSpawn, state["spawn_id"]) if state.get("spawn_id") else None
        if spawn is not None:
            spawn.current_hp = max(0, state["mob_hp"])

        if state["mob_hp"] <= 0:
            await _finish_victory(callback, session, character, mob, spawn, state)
            return

        await session.commit()

    await send_or_edit_photo(
        callback,
        f"💥 <b>ЗАКЛИНАНИЕ ПРЕРВАНО!</b>\n\n"
        f"Ты вовремя нанёс сокрушительный удар щитом ({bash_dmg} урона) и сбил {chan_name}!\n"
        f"💫 <b>{mob.name} оглушён на 1 ход!</b>\n\n"
        f"❤️ Ты: {state['character_hp']}/{character.max_hp}\n"
        f"👾 {mob.name}: {state['mob_hp']}",
        reply_markup=combat_keyboard(is_channeling=False, stance=state.get("stance", "balanced")),
        image_url=_mob_image(mob),
    )


@router.callback_query(F.data == "combat_stance_menu")
async def combat_stance_menu(callback: CallbackQuery):
    state = combat_state.get(callback.from_user.id)
    if not state:
        await callback.answer("Бой не найден.", show_alert=True)
        return
    cur = state.get("stance", "balanced")
    await safe_edit_text(
        callback,
        f"🥋 <b>Выбор боевой стойки</b>\n\n"
        f"Текущая стойка: <b>{cur}</b>\n\n"
        f"• 🗡 <b>Берсерк:</b> +30% к урону, но входящий урон выше на 20%.\n"
        f"• 🛡 <b>Парирование:</b> +25% брони и 35% шанс контратаки.\n"
        f"• 🧘 <b>Концентрация:</b> +25% к магии и восстановление маны каждый ход.",
        reply_markup=combat_stance_keyboard(cur),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("combat_set_stance:"))
async def combat_set_stance(callback: CallbackQuery):
    stance = callback.data.split(":")[1]
    state = combat_state.get(callback.from_user.id)
    if not state:
        await callback.answer("Бой не найден.", show_alert=True)
        return
    state["stance"] = stance
    await callback.answer(f"Стойка изменена на: {stance}!")
    await combat_attack(callback)


@router.callback_query(F.data == "combat_back")
async def combat_back(callback: CallbackQuery):
    state = combat_state.get(callback.from_user.id)
    if not state:
        await callback.answer("Бой не найден.", show_alert=True)
        return
    await combat_attack(callback)


@router.callback_query(F.data == "combat_flee")
async def combat_flee(callback: CallbackQuery):
    state = combat_state.pop(callback.from_user.id, None)
    if state:
        async with async_session() as session:
            character = await _load_character(session, callback.from_user.id)
            if character:
                character.current_hp = max(1, state["character_hp"])
            spawn_id = state.get("spawn_id")
            if spawn_id:
                spawn = await session.get(MobSpawn, spawn_id)
                if spawn is not None:
                    # Моб снова свободен и может пойти дальше по своим делам
                    spawn.engaged_by_id = None
            await session.commit()

    await safe_edit_text(callback, "🏃 Ты сбежал с поля боя. Жизнь дороже чести...",
        reply_markup=continue_keyboard(),
    )


@router.callback_query(F.data == "rest")
async def rest(callback: CallbackQuery):
    async with async_session() as session:
        character = await _load_character(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        heal = character.max_hp // 3
        character.current_hp = min(character.max_hp, character.current_hp + heal)
        mp_restore = character.max_mp // 3
        character.current_mp = min(character.max_mp, character.current_mp + mp_restore)
        await session.commit()

    await safe_edit_text(
        callback,
        f"🏕 <b>Отдых</b>\n\n"
        f"Ты отдохнул у костра.\n"
        f"❤️ +{heal} HP | 💙 +{mp_restore} MP\n\n"
        f"Текущее здоровье: {character.current_hp}/{character.max_hp}",
        reply_markup=continue_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "boss_fight")
async def boss_fight(callback: CallbackQuery):
    await callback.answer("Боссы появятся в следующем обновлении!", show_alert=True)
