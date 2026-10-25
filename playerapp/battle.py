"""Пошаговый бой мобильного приложения.

Тот же мир и те же правила, что в bot/handlers/battle.py: живые экземпляры
мобов берутся из MobSpawn, бой пошаговый, награды — через core.loot и
общие валюты/опыт, уровни и раны работают как у бота. Намеренно проще
полного боя бота (без стоек и школ магии) — это базовый слой API,
расширяемый новыми действиями без изменения клиентского контракта.
"""
import random

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core import death as core_death
from core import statpoints
from core.enums import BattleResult
from core.loot import give_mob_loot
from core.models import Battle, Character, MobSpawn
from core.spawns import kill_spawn, spawn_at_cell
from core.stats import attack_power, combat_stats, damage_reduction
from engine.currency import add_currency
from playerapp.service import ServiceError

# character_id -> состояние боя. Один процесс с ботом (launch.py), поэтому
# in-memory достаточно; после рестарта незаконченный бой просто закрывается.
_combat: dict[int, dict] = {}


def active_battle(character_id: int) -> dict | None:
    return _combat.get(character_id)


async def start_battle(session: AsyncSession, character: Character) -> dict:
    if character.current_hp <= 0:
        raise ServiceError("Ты слишком слаб — отдохни у костра.")
    state = _combat.get(character.id)
    if state:
        return state

    if character.cell is None:
        raise ServiceError("Герой ещё не в мире")
    spawn = await spawn_at_cell(session, character.cell)
    if not spawn or not spawn.mob:
        raise ServiceError("Здесь нет врагов.")
    if spawn.engaged_by_id and spawn.engaged_by_id != character.id:
        raise ServiceError("С этим врагом уже кто-то сражается.")

    # Атомарный захват спавна — тот же приём, что в боте.
    claimed = await session.execute(
        update(MobSpawn)
        .where(MobSpawn.id == spawn.id)
        .where(MobSpawn.is_alive.is_(True))
        .where(or_(MobSpawn.engaged_by_id.is_(None),
                   MobSpawn.engaged_by_id == character.id))
        .values(engaged_by_id=character.id)
    )
    if claimed.rowcount != 1:
        raise ServiceError("С этим врагом уже кто-то сражается.")
    spawn.engaged_by_id = character.id
    if not spawn.current_hp:
        spawn.current_hp = spawn.mob.hp
    await session.commit()

    state = {
        "spawn_id": spawn.id,
        "mob_id": spawn.mob.id,
        "mob_name": spawn.mob.name,
        "mob_hp": spawn.current_hp,
        "mob_max_hp": spawn.mob.hp,
        "mob_damage": spawn.mob.damage,
        "mob_defense": spawn.mob.defense or 0,
        "character_hp": character.current_hp,
        "rounds": 0,
        "damage_dealt": 0,
        "damage_taken": 0,
        "log": [f"⚔️ {spawn.mob.name} преграждает путь!"],
    }
    _combat[character.id] = state
    return state


def _public_state(state: dict, character: Character, finished: bool = False,
                  victory: bool = False, defeat: bool = False) -> dict:
    return {
        "active": not finished,
        "victory": victory,
        "defeat": defeat,
        "mob": {
            "name": state["mob_name"],
            "hp": max(0, state["mob_hp"]),
            "max_hp": state["mob_max_hp"],
        },
        "character_hp": character.current_hp,
        "character_max_hp": character.max_hp,
        "rounds": state["rounds"],
        "log": state["log"][-8:],
    }


async def attack(session: AsyncSession, character: Character) -> dict:
    state = _combat.get(character.id)
    if not state:
        # Нет активного боя — пробуем начать с врагом на клетке.
        state = await start_battle(session, character)

    stats = await combat_stats(session, character)
    state["rounds"] += 1

    # ── Удар героя: базовая сила + оружие, разброс ±15%, крит ──
    raw = attack_power(stats, character)
    hit = max(1, int(raw * random.uniform(0.85, 1.15)))
    is_crit = random.random() * 100 < (character.crit_chance or 0)
    if is_crit:
        hit = int(hit * (1 + (character.crit_damage or 50) / 100))
    dealt = max(1, hit - state["mob_defense"])
    state["mob_hp"] -= dealt
    state["damage_dealt"] += dealt
    state["log"].append(
        ("💥 Крит! " if is_crit else "🗡 ") +
        f"Ты наносишь {dealt} урона."
    )

    if state["mob_hp"] <= 0:
        return await _finish_victory(session, character, state, stats)

    # ── Ответный удар моба ──
    reduction = damage_reduction(stats)
    incoming = max(
        1,
        int(state["mob_damage"] * random.uniform(0.85, 1.15)) - reduction,
    )
    state["character_hp"] -= incoming
    state["damage_taken"] += incoming
    character.current_hp = max(1, state["character_hp"])
    state["log"].append(f"👹 {state['mob_name']} бьёт в ответ на {incoming}.")

    if state["character_hp"] <= 0:
        return await _finish_defeat(session, character, state)

    await session.commit()
    return _public_state(state, character)


async def flee(session: AsyncSession, character: Character) -> dict:
    state = _combat.pop(character.id, None)
    if not state:
        raise ServiceError("Ты не в бою.")
    # Шанс уйти: базово 55% + удача, потолок 90%.
    chance = min(0.9, 0.55 + (character.luck or 0) / 400)
    spawn = await session.get(MobSpawn, state["spawn_id"])
    if random.random() <= chance:
        if spawn:
            spawn.engaged_by_id = None
        character.current_hp = max(1, state["character_hp"])
        session.add(Battle(
            character_id=character.id, mob_id=state["mob_id"],
            result=BattleResult.ESCAPE, rounds=state["rounds"],
            damage_dealt=state["damage_dealt"], damage_taken=state["damage_taken"],
        ))
        await session.commit()
        return {"active": False, "escaped": True,
                "message": "🏃 Ты оторвался от погони. Жизнь дороже чести."}

    # Не удалось уйти — моб бьёт в спину, бой продолжается.
    stats = await combat_stats(session, character)
    incoming = max(
        1,
        int(state["mob_damage"] * random.uniform(0.85, 1.15))
        - damage_reduction(stats),
    )
    state["character_hp"] -= incoming
    state["damage_taken"] += incoming
    state["rounds"] += 1
    character.current_hp = max(1, state["character_hp"])
    state["log"].append(f"🏃 Побег не удался! {state['mob_name']} бьёт на {incoming}.")
    _combat[character.id] = state
    if state["character_hp"] <= 0:
        return await _finish_defeat(session, character, state)
    await session.commit()
    return _public_state(state, character)


async def _finish_victory(session, character, state, stats) -> dict:
    _combat.pop(character.id, None)
    spawn = await session.get(MobSpawn, state["spawn_id"])
    mob = spawn.mob if spawn else None
    if spawn and mob:
        await kill_spawn(session, spawn, mob)

    gold = 0
    exp = 0
    loot_names: list[str] = []
    if mob:
        if mob.gold_max and mob.gold_max >= (mob.gold_min or 0):
            gold = random.randint(mob.gold_min or 0, mob.gold_max)
        else:
            gold = int((mob.gold_reward or 0) * random.uniform(0.8, 1.2))
        exp = mob.exp_reward or 0
        add_currency(character, bronze=gold)
        loot = await give_mob_loot(session, character, mob)
        loot_names = [inv.display_name() for inv in loot]

    character.experience = (character.experience or 0) + exp
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

    character.current_hp = max(1, state["character_hp"])
    if mob:
        session.add(Battle(
            character_id=character.id, mob_id=mob.id,
            result=BattleResult.VICTORY, rounds=state["rounds"],
            damage_dealt=state["damage_dealt"], damage_taken=state["damage_taken"],
            gold_earned=gold, exp_earned=exp,
        ))
    await session.commit()

    result = _public_state(state, character, finished=True, victory=True)
    result.update({
        "gold_bronze": gold, "exp": exp,
        "levels_gained": levels_gained, "loot": loot_names,
        "message": f"🏆 Победа над {state['mob_name']}!",
    })
    return result


async def _finish_defeat(session, character, state) -> dict:
    _combat.pop(character.id, None)
    spawn = await session.get(MobSpawn, state["spawn_id"])
    if spawn:
        spawn.engaged_by_id = None
    character.current_hp = 1
    # Рана после гибели — та же механика, что у бота (статы временно срезаны).
    core_death.wound(character)
    session.add(Battle(
        character_id=character.id, mob_id=state["mob_id"],
        result=BattleResult.DEFEAT, rounds=state["rounds"],
        damage_dealt=state["damage_dealt"], damage_taken=state["damage_taken"],
    ))
    await session.commit()
    result = _public_state(state, character, finished=True, defeat=True)
    result["message"] = "💀 Ты пал в бою. Рана ослабила тебя — отдохни и вернись."
    return result
