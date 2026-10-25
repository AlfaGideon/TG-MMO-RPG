// Начало боя с мобом на текущей клетке: input { spawnId }.
import { db } from 'sdk';
import { and, eq } from 'sdk/db';
import { mobSpawns, characters } from '../schema.js';
import { requireCharacter } from '../lib/character.js';
import { buildState } from '../lib/state.js';
import { startBattle } from '../lib/battle.js';
import { tickWorld } from '../lib/world.js';

export default async function (input, ctx) {
  const { character } = await requireCharacter(ctx);
  await tickWorld();
  const spawnId = Number(input?.spawnId);
  if (!Number.isInteger(spawnId)) {
    const spawn = await db.select().from(mobSpawns)
      .where(and(
        eq(mobSpawns.locationId, character.locationId),
        eq(mobSpawns.floor, character.floor),
        eq(mobSpawns.isAlive, true),
      )).get();
    if (!spawn) return { ...(await buildState(character)), messages: ['Рядом никого нет.'] };
    await startBattle(character, spawn.id);
  } else {
    await startBattle(character, spawnId);
  }
  const refreshed = await db.select().from(characters).where(eq(characters.id, character.id)).get();
  return buildState(refreshed);
}
