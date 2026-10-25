// Переход на соседнюю клетку: input { dir: 'N'|'E'|'S'|'W' }.
import { db, EndpointError } from 'sdk';
import { and, eq } from 'sdk/db';
import { cells, characters, visited, pveBattles } from '../schema.js';
import { requireCharacter } from '../lib/character.js';
import { buildState } from '../lib/state.js';
import { tickWorld } from '../lib/world.js';

const DIRS = {
  N: { dx: 0, dy: -1 }, E: { dx: 1, dy: 0 },
  S: { dx: 0, dy: 1 }, W: { dx: -1, dy: 0 },
};

export default async function (input, ctx) {
  const { character } = await requireCharacter(ctx);
  const delta = DIRS[input?.dir];
  if (!delta) throw new EndpointError('Неизвестное направление', { code: 'BAD_DIR' });

  const battle = await db.select().from(pveBattles)
    .where(and(eq(pveBattles.characterId, character.id), eq(pveBattles.status, 'active')))
    .get();
  if (battle) throw new EndpointError('Сначала закончите бой — атакуйте или бегите.',
    { code: 'IN_BATTLE' });

  const current = await db.select().from(cells).where(eq(cells.id, character.cellId)).get();
  const targetX = current.x + delta.dx;
  const targetY = current.y + delta.dy;
  const target = await db.select().from(cells)
    .where(and(
      eq(cells.locationId, current.locationId), eq(cells.floor, current.floor),
      eq(cells.x, targetX), eq(cells.y, targetY),
    )).get();
  if (!target || !target.passable) {
    throw new EndpointError('Туда не пройти — преграда.', { code: 'BLOCKED' });
  }

  await db.update(characters).set({ cellId: target.id, updatedAt: new Date() })
    .where(eq(characters.id, character.id));
  await db.insert(visited).values({
    characterId: character.id, locationId: target.locationId,
    floor: target.floor, x: target.x, y: target.y,
  }).onConflictDoNothing({ target: [visited.characterId, visited.locationId, visited.floor, visited.x, visited.y] });

  await tickWorld();
  const refreshed = await db.select().from(characters).where(eq(characters.id, character.id)).get();
  return buildState(refreshed);
}
