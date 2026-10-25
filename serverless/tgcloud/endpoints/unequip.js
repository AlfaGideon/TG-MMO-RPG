// Снять надетый предмет: input { inventoryId }.
import { db, EndpointError } from 'sdk';
import { and, eq } from 'sdk/db';
import { inventory, items, characters } from '../schema.js';
import { requireCharacter } from '../lib/character.js';
import { buildState } from '../lib/state.js';

export default async function (input, ctx) {
  const { character } = await requireCharacter(ctx);
  const row = await db.select().from(inventory)
    .where(and(eq(inventory.id, Number(input?.inventoryId)),
      eq(inventory.characterId, character.id))).get();
  if (!row || !row.equipped) {
    throw new EndpointError('Предмет не надет.', { code: 'NOT_EQUIPPED' });
  }
  const item = await db.select().from(items).where(eq(items.id, row.itemId)).get();
  await db.update(inventory).set({ equipped: false }).where(eq(inventory.id, row.id));
  const refreshed = await db.select().from(characters).where(eq(characters.id, character.id)).get();
  return { ...(await buildState(refreshed)), messages: [`Вы сняли: ${item.name}.`] };
}
