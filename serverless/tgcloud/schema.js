// Схема SQLite Telegram Serverless.
// Правила платформы: без внешних ключей (PRAGMA foreign_keys=OFF), дроп только
// через .deprecated(), json/boolean/timestamps — через mode.
import {
  table, text, integer, boolean, json, sql,
  index, uniqueIndex, real,
} from 'sdk/db';

// ── Пользователи Telegram и их персонажи ────────────────────────────────────
export const users = table('users', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  tgId: integer('tg_id').notNull(),
  username: text('username'),
  firstName: text('first_name'),
  lang: text('lang').default('ru'),
  createdAt: integer('created_at', { mode: 'timestamp' }).default(sql`(unixepoch())`),
}, (t) => ({
  uqUsersTg: uniqueIndex('uidx_users_tg_id').on(t.tgId),
}));

export const characters = table('characters', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  userId: integer('user_id').notNull(),
  name: text('name').notNull(),
  classKey: text('class_key').notNull().default('warrior'),
  level: integer('level').notNull().default(1),
  exp: integer('exp').notNull().default(0),
  bronze: integer('bronze').notNull().default(0),
  silver: integer('silver').notNull().default(0),
  gold: integer('gold').notNull().default(0),
  hp: integer('hp').notNull().default(100),
  maxHp: integer('max_hp').notNull().default(100),
  mp: integer('mp').notNull().default(30),
  maxMp: integer('max_mp').notNull().default(30),
  str: integer('str').notNull().default(5),
  agi: integer('agi').notNull().default(5),
  int: integer('int').notNull().default(5),
  end: integer('end').notNull().default(5),
  luck: integer('luck').notNull().default(5),
  critChance: real('crit_chance').default(0.05),
  critDamage: real('crit_damage').default(1.5),
  statPoints: integer('stat_points').notNull().default(0),
  locationId: integer('location_id').notNull().default(1),
  cellId: integer('cell_id').notNull(),
  floor: integer('floor').notNull().default(1),
  woundUntil: integer('wound_until', { mode: 'timestamp' }),
  createdAt: integer('created_at', { mode: 'timestamp' }).default(sql`(unixepoch())`),
  updatedAt: integer('updated_at', { mode: 'timestamp' }).default(sql`(unixepoch())`),
}, (t) => ({
  uqCharUser: uniqueIndex('uidx_characters_user').on(t.userId),
  idxCharLoc: index('idx_characters_location').on(t.locationId),
}));

// ── Мир: локации, клетки, мобы, спавны ───────────────────────────────────────
export const locations = table('locations', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  key: text('key').notNull(),
  name: text('name').notNull(),
  description: text('description').default(''),
  sizeX: integer('size_x').notNull().default(8),
  sizeY: integer('size_y').notNull().default(8),
}, (t) => ({
  uqLocKey: uniqueIndex('uidx_locations_key').on(t.key),
}));

export const cells = table('cells', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  locationId: integer('location_id').notNull(),
  floor: integer('floor').notNull().default(1),
  x: integer('x').notNull(),
  y: integer('y').notNull(),
  passable: boolean('passable').notNull().default(true),
  tileType: text('tile_type').notNull().default('ground'), // ground|wall|rubble|water|path
  name: text('name').default(''),
  description: text('description').default(''),
  hasCampfire: boolean('has_campfire').notNull().default(false),
  hasChest: boolean('has_chest').notNull().default(false),
  chestOpenedAt: integer('chest_opened_at', { mode: 'timestamp' }),
  hasNpc: boolean('has_npc').notNull().default(false),
  npcName: text('npc_name').default(''),
  targetLocationId: integer('target_location_id'),
  targetX: integer('target_x'),
  targetY: integer('target_y'),
}, (t) => ({
  uqCell: uniqueIndex('uidx_cells_coord').on(t.locationId, t.floor, t.x, t.y),
  idxCellLoc: index('idx_cells_location').on(t.locationId, t.floor),
}));

export const mobs = table('mobs', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  key: text('key').notNull(),
  name: text('name').notNull(),
  level: integer('level').notNull().default(1),
  maxHp: integer('max_hp').notNull(),
  damage: integer('damage').notNull(),
  defense: integer('defense').notNull().default(0),
  goldMin: integer('gold_min').notNull().default(0),
  goldMax: integer('gold_max').notNull().default(5),
  expReward: integer('exp_reward').notNull().default(20),
  isBoss: boolean('is_boss').notNull().default(false),
}, (t) => ({
  uqMobKey: uniqueIndex('uidx_mobs_key').on(t.key),
}));

export const mobSpawns = table('mob_spawns', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  mobId: integer('mob_id').notNull(),
  locationId: integer('location_id').notNull(),
  floor: integer('floor').notNull().default(1),
  x: integer('x').notNull(),
  y: integer('y').notNull(),
  hp: integer('hp').notNull(),
  isAlive: boolean('is_alive').notNull().default(true),
  respawnAt: integer('respawn_at', { mode: 'timestamp' }),
  engagedBy: integer('engaged_by'), // characterId, пока идёт бой
}, (t) => ({
  idxSpawnLoc: index('idx_spawns_location').on(t.locationId, t.floor, t.x, t.y),
}));

// ── Предметы и инвентарь ─────────────────────────────────────────────────────
export const items = table('items', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  key: text('key').notNull(),
  name: text('name').notNull(),
  type: text('type').notNull(), // weapon|armor|potion|quest|misc
  rarity: text('rarity').notNull().default('common'),
  levelReq: integer('level_req').notNull().default(1),
  description: text('description').default(''),
  bonuses: json('bonuses').notNull().default({}), // {str:2, maxHp:10, damage:4,...}
  price: integer('price').notNull().default(1),
}, (t) => ({
  uqItemKey: uniqueIndex('uidx_items_key').on(t.key),
}));

export const inventory = table('inventory', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  characterId: integer('character_id').notNull(),
  itemId: integer('item_id').notNull(),
  quantity: integer('quantity').notNull().default(1),
  equipped: boolean('equipped').notNull().default(false),
  inStash: boolean('in_stash').notNull().default(false),
}, (t) => ({
  idxInvChar: index('idx_inventory_character').on(t.characterId),
  uidxInvSlot: uniqueIndex('uidx_inventory_slot')
    .on(t.characterId, t.itemId, t.inStash),
}));

// ── Бой и туман войны ────────────────────────────────────────────────────────
// Изоляты serverless не разделяют память: состояние боя живёт в БД.
export const pveBattles = table('pve_battles', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  characterId: integer('character_id').notNull(),
  spawnId: integer('spawn_id').notNull(),
  mobHp: integer('mob_hp').notNull(),
  round: integer('round').notNull().default(0),
  damageDealt: integer('damage_dealt').notNull().default(0),
  damageTaken: integer('damage_taken').notNull().default(0),
  log: json('log').notNull().default([]),
  status: text('status').notNull().default('active'), // active|won|lost|fled
  updatedAt: integer('updated_at', { mode: 'timestamp' }).default(sql`(unixepoch())`),
}, (t) => ({
  uqBattleChar: uniqueIndex('uidx_battles_character').on(t.characterId),
}));

export const visited = table('visited', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  characterId: integer('character_id').notNull(),
  locationId: integer('location_id').notNull(),
  floor: integer('floor').notNull().default(1),
  x: integer('x').notNull(),
  y: integer('y').notNull(),
}, (t) => ({
  uqVisited: uniqueIndex('uidx_visited_cell')
    .on(t.characterId, t.locationId, t.floor, t.x, t.y),
}));
