// Сборка полного состояния для экрана Mini App: персонаж, клетка, соседи,
// туман войны, активный бой, инвентарь. Один контракт на все action-endpoints.
import { db } from 'sdk';
import { and, eq, inArray } from 'sdk/db';
import {
  cells, mobSpawns, mobs, pveBattles, inventory, items, visited,
} from '../schema.js';
import { neighborCoords } from './world.js';
import { effectiveStats } from './progression.js';

async function cellById(id) {
  return db.select().from(cells).where(eq(cells.id, id)).get();
}

async function aliveSpawnAt(locationId, floor, x, y) {
  const spawn = await db.select().from(mobSpawns)
    .where(and(
      eq(mobSpawns.locationId, locationId), eq(mobSpawns.floor, floor),
      eq(mobSpawns.x, x), eq(mobSpawns.y, y), eq(mobSpawns.isAlive, true),
    )).get();
  if (!spawn) return null;
  const mob = await db.select().from(mobs).where(eq(mobs.id, spawn.mobId)).get();
  return { spawnId: spawn.id, mob, hp: spawn.hp };
}

export async function buildState(character) {
  const current = await cellById(character.cellId);

  // Туман войны: набор посещённых координат.
  const seenRows = await db.select().from(visited)
    .where(eq(visited.characterId, character.id));
  const seen = new Set(seenRows.map((r) => `${r.x},${r.y}`));

  // Соседние клетки: стены видно, содержимое — только если уже посещена.
  const neighbors = [];
  for (const n of neighborCoords(current.x, current.y)) {
    const cell = await db.select().from(cells)
      .where(and(
        eq(cells.locationId, current.locationId), eq(cells.floor, current.floor),
        eq(cells.x, n.x), eq(cells.y, n.y),
      )).get();
    if (!cell) continue;
    const isSeen = seen.has(`${n.x},${n.y}`);
    const entry = {
      dir: n.dir, label: n.label, x: n.x, y: n.y,
      passable: cell.passable, tileType: cell.tileType,
      visible: isSeen || cell.tileType === 'wall',
    };
    if (isSeen && cell.passable) {
      const spawn = await aliveSpawnAt(current.locationId, current.floor, n.x, n.y);
      if (spawn) entry.mob = { name: spawn.mob.name, level: spawn.mob.level, isBoss: spawn.mob.isBoss };
      if (cell.hasCampfire) entry.campfire = true;
      if (cell.hasChest) entry.chest = true;
      if (cell.hasNpc) entry.npc = cell.npcName;
    }
    neighbors.push(entry);
  }

  const hereSpawn = await aliveSpawnAt(current.locationId, current.floor, current.x, current.y);

  // Активный бой + данные моба.
  let battle = null;
  const battleRow = await db.select().from(pveBattles)
    .where(and(eq(pveBattles.characterId, character.id), eq(pveBattles.status, 'active')))
    .get();
  if (battleRow) {
    const spawn = await db.select().from(mobSpawns).where(eq(mobSpawns.id, battleRow.spawnId)).get();
    const mob = spawn ? await db.select().from(mobs).where(eq(mobs.id, spawn.mobId)).get() : null;
    battle = { ...battleRow, mob };
  }

  // Инвентарь с данными предметов.
  const invRows = await db.select().from(inventory)
    .where(eq(inventory.characterId, character.id));
  const itemRows = invRows.length
    ? await db.select().from(items).where(inArray(items.id, invRows.map((r) => r.itemId)))
    : [];
  const itemById = new Map(itemRows.map((i) => [i.id, i]));
  const bag = invRows.map((r) => ({ ...r, item: itemById.get(r.itemId) }))
    .filter((r) => r.item);
  const equipped = bag.filter((r) => r.equipped && r.item.bonuses);
  const stats = effectiveStats(character, equipped.map((r) => r.item));

  return {
    character,
    stats,
    cell: {
      id: current.id, x: current.x, y: current.y,
      name: current.name, description: current.description,
      tileType: current.tileType,
      campfire: current.hasCampfire,
      chest: current.hasChest && !current.chestOpenedAt,
      npc: current.hasNpc ? current.npcName : null,
      mob: hereSpawn ? { spawnId: hereSpawn.spawnId, ...hereSpawn.mob, hp: hereSpawn.hp } : null,
    },
    neighbors,
    battle,
    inventory: bag,
    seen: [...seen],
  };
}
