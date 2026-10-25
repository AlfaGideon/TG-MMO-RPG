// GET-семантика через POST /api/getProfile — полное состояние экрана.
import { requireCharacter } from '../lib/character.js';
import { buildState } from '../lib/state.js';
import { tickWorld } from '../lib/world.js';

export default async function (_input, ctx) {
  const { character } = await requireCharacter(ctx);
  await tickWorld();
  return buildState(character);
}
