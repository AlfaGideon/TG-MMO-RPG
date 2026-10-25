// Чистая математика прогресса и боя — без sdk, юнит-тестируется локально.
import { GAME, CLASSES } from './config.js';

export function expToNext(level) {
  return GAME.EXP_CURVE(level);
}

// Начисляет опыт, возвращает { exp, level, statPoints, levelsGained }.
export function applyExp(character, gained) {
  let { exp, level, statPoints } = character;
  exp += gained;
  let levelsGained = 0;
  while (exp >= expToNext(level) && level < 50) {
    exp -= expToNext(level);
    level += 1;
    levelsGained += 1;
    statPoints += GAME.STAT_POINTS_PER_LEVEL;
  }
  return { exp, level, statPoints, levelsGained };
}

// Базовый урон атаки с учётом защиты и крита. rng — функция из makeRng.
export function rollAttack(rng, attacker, defenderDefense) {
  const variance = 0.85 + rng() * 0.3; // 0.85–1.15
  const base = Math.max(1, attacker.damage - defenderDefense);
  const isCrit = rng() < (attacker.critChance ?? 0.05);
  let damage = Math.round(base * variance);
  if (isCrit) damage = Math.round(damage * (attacker.critDamage ?? 1.5));
  return { damage: Math.max(1, damage), isCrit };
}

// Урон моба по персонажу: защита собирается из end и экипировки.
export function rollMobAttack(rng, mobDamage, characterDefense) {
  const variance = 0.85 + rng() * 0.3;
  return Math.max(1, Math.round(Math.max(1, mobDamage - characterDefense) * variance));
}

export function rollFlee(rng, characterAgi) {
  const bonus = Math.min(0.25, characterAgi * 0.01);
  return rng() < GAME.FLEE_BASE_CHANCE + bonus;
}

export function classTemplate(classKey) {
  return CLASSES[classKey] ?? CLASSES.warrior;
}

// Суммарные боевые характеристики с бонусами экипировки.
export function effectiveStats(character, equippedBonuses = []) {
  const b = equippedBonuses.reduce((acc, item) => {
    for (const [k, v] of Object.entries(item.bonuses || {})) {
      acc[k] = (acc[k] ?? 0) + v;
    }
    return acc;
  }, {});
  return {
    damage: character.str * 2 + (b.damage ?? 0),
    defense: Math.floor(character.end / 2) + (b.defense ?? 0),
    critChance: character.critChance + (b.critChance ?? 0),
    critDamage: character.critDamage,
    maxHpBonus: b.maxHp ?? 0,
    agi: character.agi,
  };
}

// Награда за убийство: бронза в пределах дропа моба.
export function rollLoot(rng, mob) {
  const bronze = mob.goldMin + Math.floor(rng() * (mob.goldMax - mob.goldMin + 1));
  return { bronze, exp: mob.expReward };
}
