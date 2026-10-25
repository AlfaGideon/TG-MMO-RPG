// Попытка побега из активного боя.
import { db } from 'sdk';
import { eq } from 'sdk/db';
import { characters } from '../schema.js';
import { requireCharacter } from '../lib/character.js';
import { buildState } from '../lib/state.js';
import { flee } from '../lib/battle.js';

export default async function (_input, ctx) {
  const { character } = await requireCharacter(ctx);
  const fleeResult = await flee(character);
  const refreshed = await db.select().from(characters).where(eq(characters.id, character.id)).get();
  const state = await buildState(refreshed);
  return { ...state, fleeResult };
}
