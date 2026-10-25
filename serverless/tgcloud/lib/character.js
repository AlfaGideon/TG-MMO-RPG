// Доступ к пользователям и персонажам, создание первого героя.
import { db, EndpointError } from 'sdk';
import { eq } from 'sdk/db';
import { users, characters, cells, visited } from '../schema.js';
import { classTemplate } from './progression.js';
import { ensureWorld } from './world.js';

export async function getOrCreateUser(tgUser, lang = 'ru') {
  let user = await db.select().from(users).where(eq(users.tgId, tgUser.id)).get();
  if (user) {
    const patch = {};
    if (tgUser.username && user.username !== tgUser.username) patch.username = tgUser.username;
    if (tgUser.first_name && user.firstName !== tgUser.first_name) patch.firstName = tgUser.first_name;
    if (Object.keys(patch).length) await db.update(users).set(patch).where(eq(users.id, user.id));
    return user;
  }
  const inserted = await db.insert(users).values({
    tgId: tgUser.id,
    username: tgUser.username ?? null,
    firstName: tgUser.first_name ?? 'Странник',
    lang,
  }).returning();
  return inserted[0];
}

export async function createCharacter(user, name, classKey = 'warrior') {
  await ensureWorld();
  const tpl = classTemplate(classKey);
  // Стартовая клетка — лагерный костёр (1,1) первой локации.
  const start = await db.select().from(cells)
    .where(eq(cells.hasCampfire, true)).get();
  const inserted = await db.insert(characters).values({
    userId: user.id,
    name: name.slice(0, 32),
    classKey,
    hp: tpl.maxHp, maxHp: tpl.maxHp,
    mp: tpl.maxMp, maxMp: tpl.maxMp,
    str: tpl.str, agi: tpl.agi, int: tpl.int, end: tpl.end, luck: tpl.luck,
    critChance: tpl.critChance, critDamage: tpl.critDamage,
    locationId: start.locationId, cellId: start.id, floor: start.floor,
    bronze: 0, silver: 0, gold: 0,
  }).returning();
  await db.insert(visited).values({
    characterId: inserted[0].id,
    locationId: start.locationId, floor: start.floor,
    x: start.x, y: start.y,
  });
  return inserted[0];
}

export async function getCharacterForTgId(tgId) {
  const user = await db.select().from(users).where(eq(users.tgId, tgId)).get();
  if (!user) return null;
  const character = await db.select().from(characters)
    .where(eq(characters.userId, user.id)).get();
  return character ? { user, character } : { user, character: null };
}

// Endpoint-вариант: достоверный пользователь из initData, иначе 400.
export async function requireCharacter(ctx) {
  const tgUser = ctx?.initData?.user;
  if (!tgUser?.id) throw new EndpointError('Нет данных пользователя Telegram', { code: 'NO_USER' });
  const pair = await getCharacterForTgId(tgUser.id);
  if (!pair?.character) {
    throw new EndpointError('Персонаж не создан. Откройте бота и отправьте /start.',
      { code: 'NO_CHARACTER' });
  }
  return pair;
}

export function publicCharacter(character) {
  const { id, userId, woundUntil, ...safe } = character;
  return safe;
}
