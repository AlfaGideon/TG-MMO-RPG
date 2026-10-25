// Надеть предмет экипировки: input { inventoryId }. Один тип — один слот.
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
  if (!row) throw new EndpointError('Предмет не найден в инвентаре.', { code: 'NO_ITEM' });
  const item = await db.select().from(items).where(eq(items.id, row.itemId)).get();
  if (!['weapon', 'armor', 'misc'].includes(item.type)) {
    throw new EndpointError('Это нельзя надеть — используйте кнопку «Использовать».',
      { code: 'NOT_EQUIPPABLE' });
  }
  if (character.level < item.levelReq) {
    throw new EndpointError(`Требуется уровень ${item.levelReq}.`, { code: 'LOW_LEVEL' });
  }

  // Снимаем ранее надетый предмет того же типа.
  const bag = await db.select().from(inventory)
    .where(and(eq(inventory.characterId, character.id), eq(inventory.equipped, true)));
  for (const worn of bag) {
    const wornItem = await db.select().from(items).where(eq(items.id, worn.itemId)).get();
    if (wornItem.type === item.type) {
      await db.update(inventory).set({ equipped: false }).where(eq(inventory.id, worn.id));
    }
  }
  await db.update(inventory).set({ equipped: true }).where(eq(inventory.id, row.id));

  // maxHp-бонус применяем к максимальному HP, текущее не лечим сверх лимита.
  await db.update(characters).set({ updatedAt: new Date() })
    .where(eq(characters.id, character.id));
  const refreshed = await db.select().from(characters).where(eq(characters.id, character.id)).get();
  return { ...(await buildState(refreshed)), messages: [`Вы надели: ${item.name}.`] };
}
