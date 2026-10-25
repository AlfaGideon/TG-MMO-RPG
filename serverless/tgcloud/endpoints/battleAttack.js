// Один раунд боя: удар игрока и ответ моба. Итог — в поле battleResult.
import { db } from 'sdk';
import { eq } from 'sdk/db';
import { characters } from '../schema.js';
import { requireCharacter } from '../lib/character.js';
import { buildState } from '../lib/state.js';
import { attack } from '../lib/battle.js';

export default async function (_input, ctx) {
  const { character } = await requireCharacter(ctx);
  const battleResult = await attack(character);
  const refreshed = await db.select().from(characters).where(eq(characters.id, character.id)).get();
  const state = await buildState(refreshed);
  return { ...state, battleResult };
}
