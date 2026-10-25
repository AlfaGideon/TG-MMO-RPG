// Идемпотентный сид стартового мира: одна локация 8x8, мобы, спавны, предметы.
// Вызывается из /start и из ensure-access, чтобы мир существовал до первого боя.
import { db } from 'sdk';
import { and, eq } from 'sdk/db';
import {
  locations, cells, mobs, mobSpawns, items,
} from '../schema.js';
import { makeRng, intBetween } from './rng.js';
import { GAME } from './config.js';

const SIZE = 8;

const MOB_DEFS = [
  { key: 'rat',      name: 'Чумная крыса',   level: 1, maxHp: 25,  damage: 6,  defense: 0, goldMin: 1, goldMax: 4,  expReward: 15 },
  { key: 'wolf',     name: 'Серый волк',     level: 2, maxHp: 45,  damage: 10, defense: 1, goldMin: 3, goldMax: 8,  expReward: 28 },
  { key: 'skeleton', name: 'Скелет-воин',    level: 3, maxHp: 70,  damage: 14, defense: 3, goldMin: 6, goldMax: 14, expReward: 45 },
  { key: 'wraith',   name: 'Бесплотный дух', level: 4, maxHp: 95,  damage: 18, defense: 4, goldMin: 10, goldMax: 20, expReward: 65 },
  { key: 'shade',    name: 'Рыцарь Теней',   level: 5, maxHp: 160, damage: 24, defense: 6, goldMin: 25, goldMax: 45, expReward: 120, isBoss: true },
];

const ITEM_DEFS = [
  { key: 'hp_potion', name: 'Зелье лечения', type: 'potion', rarity: 'common', levelReq: 1, price: 12, description: 'Восстанавливает 40 HP', bonuses: { heal: 40 } },
  { key: 'mp_potion', name: 'Зелье маны', type: 'potion', rarity: 'common', levelReq: 1, price: 10, description: 'Восстанавливает 30 MP', bonuses: { mana: 30 } },
  { key: 'rusty_sword', name: 'Ржавый меч', type: 'weapon', rarity: 'common', levelReq: 1, price: 20, description: 'Старый, но ещё рубит', bonuses: { damage: 3 } },
  { key: 'iron_sword', name: 'Железный меч', type: 'weapon', rarity: 'uncommon', levelReq: 3, price: 75, description: 'Надёжная сталь', bonuses: { damage: 7, str: 1 } },
  { key: 'leather_armor', name: 'Кожаная броня', type: 'armor', rarity: 'common', levelReq: 1, price: 35, description: 'Лёгкая защита', bonuses: { defense: 3, maxHp: 15 } },
  { key: 'knight_armor', name: 'Латы рыцаря', type: 'armor', rarity: 'rare', levelReq: 4, price: 140, description: 'Тяжёлая броня сумеречных рыцарей', bonuses: { defense: 8, maxHp: 40, end: 2 } },
  { key: 'shadow_ring', name: 'Кольцо теней', type: 'misc', rarity: 'epic', levelReq: 5, price: 220, description: 'Грани мира истончаются вокруг владельца', bonuses: { critChance: 0.05, agi: 3, luck: 2 } },
];

export async function ensureWorld() {
  const existing = await db.$count(locations);
  if (existing > 0) return;

  const loc = await db.insert(locations).values({
    key: 'twilight_ruins',
    name: 'Сумеречные руины',
    description: 'Развалины на границе Теней. Костёр мерцает у западных ворот.',
    sizeX: SIZE, sizeY: SIZE,
  }).returning({ id: locations.id });
  const locationId = loc[0].id;

  const rng = makeRng(20261026);
  const rubble = new Set(['2,3', '3,3', '5,5', '4,6', '6,4', '2,5', '5,1'].map((k) => k));
  const rows = [];
  for (let y = 0; y < SIZE; y += 1) {
    for (let x = 0; x < SIZE; x += 1) {
      const border = x === 0 || y === 0 || x === SIZE - 1 || y === SIZE - 1;
      const row = {
        locationId, floor: 1, x, y,
        passable: !border && !rubble.has(`${x},${y}`),
        tileType: border ? 'wall' : (rubble.has(`${x},${y}`) ? 'rubble' : 'ground'),
        name: '', description: '',
      };
      if (x === 1 && y === 1) {
        row.hasCampfire = true; row.tileType = 'path';
        row.name = 'Лагерный костёр';
        row.description = 'Безопасный привал. Здесь можно отдохнуть и вернуться после поражения.';
      } else if (x === 6 && y === 2) {
        row.hasChest = true;
        row.name = 'Древний сундук';
        row.description = 'Окованный медью сундук. Похоже, его ещё не открывали.';
      } else if (x === 1 && y === 6) {
        row.hasNpc = true; row.npcName = 'Странствующий торговец';
        row.name = 'Торговец';
        row.description = 'Пока молчит и осматривает развалины. Торговля появится позже.';
      } else if (x === 7 && y === 7) {
        row.name = 'Тёмный портал';
        row.description = 'Граница мира дрожит. Следующая локация ещё не восстановлена.';
      } else if (!border && row.passable) {
        row.description = 'Мшистые камни, пыль и тишина.';
      }
      rows.push(row);
    }
  }
  await db.insert(cells).values(rows);

  const mobIds = {};
  for (const def of MOB_DEFS) {
    const inserted = await db.insert(mobs).values(def).returning({ id: mobs.id, key: mobs.key });
    mobIds[inserted[0].key] = inserted[0].id;
  }

  const spawnPlan = [
    ['rat', 2, 2], ['rat', 3, 5], ['wolf', 4, 2], ['wolf', 5, 4],
    ['skeleton', 4, 4], ['wraith', 6, 6], ['shade', 6, 5],
  ];
  await db.insert(mobSpawns).values(spawnPlan.map(([key, x, y]) => {
    const def = MOB_DEFS.find((m) => m.key === key);
    return {
      mobId: mobIds[key], locationId, floor: 1, x, y,
      hp: def.maxHp, isAlive: true,
    };
  }));

  await db.insert(items).values(ITEM_DEFS);
}

export async function getCell(locationId, floor, x, y) {
  return db.select().from(cells)
    .where(and(eq(cells.locationId, locationId), eq(cells.floor, floor),
      eq(cells.x, x), eq(cells.y, y)))
    .get();
}

// Возвращает к жизни мобов и сундуки, чьи таймеры истекли. Вызывается из
// action-endpoints, чтобы фоновых задач не требовалось.
export async function tickWorld() {
  const now = new Date();
  const dueSpawns = await db.select().from(mobSpawns)
    .where(eq(mobSpawns.isAlive, false)).all();
  for (const spawn of dueSpawns) {
    if (spawn.respawnAt && new Date(spawn.respawnAt) <= now) {
      const mob = await db.select().from(mobs).where(eq(mobs.id, spawn.mobId)).get();
      await db.update(mobSpawns)
        .set({ isAlive: true, hp: mob.maxHp, respawnAt: null, engagedBy: null })
        .where(eq(mobSpawns.id, spawn.id));
    }
  }
  const openedChests = await db.select().from(cells)
    .where(eq(cells.hasChest, true)).all();
  for (const cell of openedChests) {
    if (cell.chestOpenedAt
      && (now - new Date(cell.chestOpenedAt)) >= GAME.CHEST_RESPAWN_SEC * 1000) {
      await db.update(cells).set({ chestOpenedAt: null }).where(eq(cells.id, cell.id));
    }
  }
}

export function neighborCoords(x, y) {
  return [
    { dir: 'N', dx: 0, dy: -1, label: 'Север' },
    { dir: 'E', dx: 1, dy: 0, label: 'Восток' },
    { dir: 'S', dx: 0, dy: 1, label: 'Юг' },
    { dir: 'W', dx: -1, dy: 0, label: 'Запад' },
  ].map((c) => ({ ...c, x: x + c.dx, y: y + c.dy }));
}

export { intBetween, GAME };
