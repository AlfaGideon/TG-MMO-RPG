// Боевые операции. Состояние каждого боя — строка pve_battles, потому что
// изоляты Telegram Serverless не разделяют память между запросами Mini App.
import { db, EndpointError } from 'sdk';
import { and, eq, inArray } from 'sdk/db';
import {
  cells, mobSpawns, mobs, pveBattles, characters, inventory, items,
} from '../schema.js';
import {
  rollAttack, rollMobAttack, rollFlee, applyExp, rollLoot, effectiveStats,
} from './progression.js';
import { makeRng, randomSeed } from './rng.js';
import { GAME } from './config.js';

async function activeBattle(characterId) {
  return db.select().from(pveBattles)
    .where(and(eq(pveBattles.characterId, characterId), eq(pveBattles.status, 'active')))
    .get();
}

async function equippedBonuses(characterId) {
  const rows = await db.select().from(inventory)
    .where(and(eq(inventory.characterId, characterId), eq(inventory.equipped, true)));
  const ids = rows.map((r) => r.itemId);
  if (!ids.length) return [];
  return db.select().from(items).where(inArray(items.id, ids));
}

export async function startBattle(character, spawnId) {
  const existing = await activeBattle(character.id);
  if (existing) throw new EndpointError('Бой уже идёт', { code: 'IN_BATTLE' });

  const spawn = await db.select().from(mobSpawns).where(eq(mobSpawns.id, spawnId)).get();
  if (!spawn || !spawn.isAlive) {
    throw new EndpointError('Цель уже мертва или недоступна', { code: 'TARGET_GONE' });
  }
  const mob = await db.select().from(mobs).where(eq(mobs.id, spawn.mobId)).get();
  await db.insert(pveBattles).values({
    characterId: character.id, spawnId, mobHp: spawn.hp,
    round: 0, log: [`Вы вступаете в бой с «${mob.name}».`], status: 'active',
  });
  await db.update(mobSpawns).set({ engagedBy: character.id }).where(eq(mobSpawns.id, spawnId));
  return { mobName: mob.name };
}

export async function attack(character) {
  const battle = await activeBattle(character.id);
  if (!battle) throw new EndpointError('Активного боя нет', { code: 'NO_BATTLE' });
  const spawn = await db.select().from(mobSpawns).where(eq(mobSpawns.id, battle.spawnId)).get();
  const mob = await db.select().from(mobs).where(eq(mobs.id, spawn.mobId)).get();
  const rng = makeRng(randomSeed(character.id + battle.round));
  const log = [...battle.log];

  const bonuses = await equippedBonuses(character.id);
  const stats = effectiveStats(character, bonuses);
  const playerHit = rollAttack(rng, stats, mob.defense);
  const mobHp = Math.max(0, battle.mobHp - playerHit.damage);
  log.push(playerHit.isCrit
    ? `КРИТ! Вы наносите ${playerHit.damage} урона «${mob.name}».`
    : `Вы наносите ${playerHit.damage} урона «${mob.name}».`);

  let result = { status: 'active' };

  if (mobHp <= 0) {
    const loot = rollLoot(rng, mob);
    const progress = applyExp(character, loot.exp);
    const update = {
      exp: progress.exp, level: progress.level, statPoints: progress.statPoints,
      bronze: character.bronze + loot.bronze,
      updatedAt: new Date(),
    };
    await db.update(characters).set(update).where(eq(characters.id, character.id));
    await db.update(pveBattles).set({
      mobHp: 0, status: 'won', round: battle.round + 1,
      damageDealt: battle.damageDealt + playerHit.damage,
      log: [...log, `«${mob.name}» повержен! +${loot.exp} опыта, +${loot.bronze} бронзы.`],
      updatedAt: new Date(),
    }).where(eq(pveBattles.id, battle.id));
    await db.update(mobSpawns).set({
      isAlive: false, hp: 0, engagedBy: null,
      respawnAt: new Date(Date.now() + GAME.MOB_RESPAWN_SEC * 1000),
    }).where(eq(mobSpawns.id, spawn.id));
    return {
      ...result, status: 'won', mobName: mob.name, loot,
      leveledUp: progress.levelsGained,
    };
  }

  // Ответный удар моба.
  const mobDamage = rollMobAttack(rng, mob.damage, stats.defense);
  const hp = Math.max(0, character.hp - mobDamage);
  log.push(`«${mob.name}» бьёт в ответ на ${mobDamage}.`);
  await db.update(characters).set({ hp, updatedAt: new Date() }).where(eq(characters.id, character.id));
  await db.update(pveBattles).set({
    mobHp, round: battle.round + 1,
    damageDealt: battle.damageDealt + playerHit.damage,
    damageTaken: battle.damageTaken + mobDamage,
    log: log.slice(-12), updatedAt: new Date(),
  }).where(eq(pveBattles.id, battle.id));
  await db.update(mobSpawns).set({ hp: mobHp }).where(eq(mobSpawns.id, spawn.id));

  if (hp <= 0) {
    const bronzeLeft = Math.floor(character.bronze * (1 - GAME.DEATH_BRONZE_LOSS));
    const lost = character.bronze - bronzeLeft;
    const campfire = await db.select().from(cells).where(eq(cells.hasCampfire, true)).get();
    await db.update(characters).set({
      hp: Math.round(character.maxHp * GAME.RESPAWN_HP_RATIO),
      bronze: bronzeLeft, cellId: campfire.id, locationId: campfire.locationId,
      woundUntil: new Date(Date.now() + 60 * 1000),
      updatedAt: new Date(),
    }).where(eq(characters.id, character.id));
    await db.update(pveBattles).set({ status: 'lost', updatedAt: new Date() })
      .where(eq(pveBattles.id, battle.id));
    await db.update(mobSpawns).set({ engagedBy: null }).where(eq(mobSpawns.id, spawn.id));
    return { ...result, status: 'lost', lostBronze: lost, mobName: mob.name };
  }
  return result;
}

export async function flee(character) {
  const battle = await activeBattle(character.id);
  if (!battle) throw new EndpointError('Активного боя нет', { code: 'NO_BATTLE' });
  const rng = makeRng(randomSeed(character.id * 7 + battle.round));
  const spawn = await db.select().from(mobSpawns).where(eq(mobSpawns.id, battle.spawnId)).get();
  const mob = await db.select().from(mobs).where(eq(mobs.id, spawn.mobId)).get();

  if (rollFlee(rng, character.agi)) {
    await db.update(pveBattles).set({ status: 'fled', updatedAt: new Date() })
      .where(eq(pveBattles.id, battle.id));
    await db.update(mobSpawns).set({ engagedBy: null }).where(eq(mobSpawns.id, spawn.id));
    return { escaped: true };
  }
  const penalty = Math.max(1, Math.round(mob.maxHp * GAME.FLEE_HP_PENALTY * 0.1) + mob.damage);
  const hp = Math.max(0, character.hp - penalty);
  await db.update(characters).set({ hp, updatedAt: new Date() }).where(eq(characters.id, character.id));
  await db.update(pveBattles).set({
    round: battle.round + 1, damageTaken: battle.damageTaken + penalty,
    log: [...battle.log, `Побег не удался! «${mob.name}» наказывает на ${penalty} урона.`].slice(-12),
    updatedAt: new Date(),
  }).where(eq(pveBattles.id, battle.id));
  if (hp <= 0) {
    const campfire = await db.select().from(cells).where(eq(cells.hasCampfire, true)).get();
    await db.update(characters).set({
      hp: Math.round(character.maxHp * GAME.RESPAWN_HP_RATIO),
      cellId: campfire.id, locationId: campfire.locationId,
      woundUntil: new Date(Date.now() + 60 * 1000),
      updatedAt: new Date(),
    }).where(eq(characters.id, character.id));
    await db.update(pveBattles).set({ status: 'lost', updatedAt: new Date() })
      .where(eq(pveBattles.id, battle.id));
    await db.update(mobSpawns).set({ engagedBy: null }).where(eq(mobSpawns.id, spawn.id));
    return { escaped: false, status: 'lost' };
  }
  return { escaped: false, penalty };
}
