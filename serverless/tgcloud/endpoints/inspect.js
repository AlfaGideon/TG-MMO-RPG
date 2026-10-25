// Осмотр клетки и открытие сундука. Возвращает state + сообщение о находке.
import { db, EndpointError } from 'sdk';
import { eq } from 'sdk/db';
import { cells, characters, items, inventory } from '../schema.js';
import { requireCharacter } from '../lib/character.js';
import { buildState } from '../lib/state.js';
import { makeRng, randomSeed, intBetween } from '../lib/rng.js';

export default async function (_input, ctx) {
  const { character } = await requireCharacter(ctx);
  const cell = await db.select().from(cells).where(eq(cells.id, character.cellId)).get();
  const messages = [];

  if (cell.hasChest && !cell.chestOpenedAt) {
    const rng = makeRng(randomSeed(cell.id));
    const bronze = intBetween(rng, 10, 30);
    await db.update(characters)
      .set({ bronze: character.bronze + bronze, updatedAt: new Date() })
      .where(eq(characters.id, character.id));
    await db.update(cells).set({ chestOpenedAt: new Date() }).where(eq(cells.id, cell.id));
    messages.push(`В сундуке нашлось ${bronze} бронзы.`);

    if (rng() < 0.6) {
      const potion = await db.select().from(items).where(eq(items.key, 'hp_potion')).get();
      const existing = await db.select().from(inventory)
        .where(eq(inventory.itemId, potion.id)).get();
      if (existing) {
        await db.update(inventory).set({ quantity: existing.quantity + 1 })
          .where(eq(inventory.id, existing.id));
      } else {
        await db.insert(inventory).values({
          characterId: character.id, itemId: potion.id, quantity: 1,
        });
      }
      messages.push('И зелье лечения — пригодится.');
    }
  } else if (cell.description) {
    messages.push(cell.description);
  }

  const refreshed = await db.select().from(characters).where(eq(characters.id, character.id)).get();
  const state = await buildState(refreshed);
  return { ...state, messages };
}
