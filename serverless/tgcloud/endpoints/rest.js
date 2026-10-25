// Отдых у лагерного костра: восстанавливает HP/MP, снимает ранение.
import { db, EndpointError } from 'sdk';
import { eq } from 'sdk/db';
import { cells, characters } from '../schema.js';
import { requireCharacter } from '../lib/character.js';
import { buildState } from '../lib/state.js';
import { GAME } from '../lib/config.js';

export default async function (_input, ctx) {
  const { character } = await requireCharacter(ctx);
  const cell = await db.select().from(cells).where(eq(cells.id, character.cellId)).get();
  if (!cell.hasCampfire) {
    throw new EndpointError('Отдыхать можно только у лагерного костра.', { code: 'NO_CAMPFIRE' });
  }
  const hp = Math.min(character.maxHp,
    character.hp + Math.round(character.maxHp * GAME.REST_HP_RATIO));
  const mp = Math.min(character.maxMp,
    character.mp + Math.round(character.maxMp * GAME.REST_MP_RATIO));
  await db.update(characters)
    .set({ hp, mp, woundUntil: null, updatedAt: new Date() })
    .where(eq(characters.id, character.id));
  const refreshed = await db.select().from(characters).where(eq(characters.id, character.id)).get();
  return { ...(await buildState(refreshed)), messages: ['Вы отдохнули у костра. Силы вернулись.'] };
}
