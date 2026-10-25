// Использовать расходник (зелья): input { inventoryId }.
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
  if (!row) throw new EndpointError('Предмет не найден.', { code: 'NO_ITEM' });
  const item = await db.select().from(items).where(eq(items.id, row.itemId)).get();
  if (item.type !== 'potion') {
    throw new EndpointError('Этот предмет не расходуется.', { code: 'NOT_USABLE' });
  }

  const patch = { updatedAt: new Date() };
  const messages = [];
  if (item.bonuses.heal) {
    patch.hp = Math.min(character.maxHp, character.hp + item.bonuses.heal);
    messages.push(`+${item.bonuses.heal} HP`);
  }
  if (item.bonuses.mana) {
    patch.mp = Math.min(character.maxMp, character.mp + item.bonuses.mana);
    messages.push(`+${item.bonuses.mana} MP`);
  }
  await db.update(characters).set(patch).where(eq(characters.id, character.id));

  if (row.quantity <= 1) {
    await db.delete(inventory).where(eq(inventory.id, row.id));
  } else {
    await db.update(inventory).set({ quantity: row.quantity - 1 }).where(eq(inventory.id, row.id));
  }
  const refreshed = await db.select().from(characters).where(eq(characters.id, character.id)).get();
  return { ...(await buildState(refreshed)), messages: [`${item.name}: ${messages.join(', ')}.`] };
}
