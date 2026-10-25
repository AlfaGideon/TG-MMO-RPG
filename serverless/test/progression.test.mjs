// Юнит-тесты чистой игровой математики. Модули без sdk-зависимостей.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { makeRng, intBetween, chance } from '../tgcloud/lib/rng.js';
import {
  applyExp, rollAttack, rollMobAttack, rollFlee, effectiveStats, expToNext,
} from '../tgcloud/lib/progression.js';

test('makeRng детерминирован при одном seed', () => {
  const a = makeRng(42);
  const b = makeRng(42);
  const seqA = [a(), a(), a()];
  const seqB = [b(), b(), b()];
  assert.deepEqual(seqA, seqB);
  assert.ok(seqA.every((v) => v >= 0 && v < 1));
});

test('intBetween держит границы', () => {
  const rng = makeRng(7);
  for (let i = 0; i < 200; i += 1) {
    const v = intBetween(rng, 5, 9);
    assert.ok(v >= 5 && v <= 9);
  }
});

test('chance соответствует вероятности', () => {
  const rng = makeRng(99);
  let hits = 0;
  for (let i = 0; i < 1000; i += 1) if (chance(rng, 0.3)) hits += 1;
  assert.ok(hits > 220 && hits < 380);
});

test('applyExp повышает уровень и начисляет очки', () => {
  const char = { exp: 0, level: 1, statPoints: 0 };
  const r1 = applyExp(char, 100); // ровно уровень
  assert.equal(r1.level, 2);
  assert.equal(r1.exp, 0);
  assert.equal(r1.statPoints, 3);
  assert.equal(r1.levelsGained, 1);

  const r2 = applyExp({ exp: 0, level: 1, statPoints: 0 }, 300); // 2 уровня: 300 - 100 - 200
  assert.equal(r2.level, 3);
  assert.equal(r2.levelsGained, 2);
  assert.equal(r2.statPoints, 6);
  assert.equal(r2.exp, 0);
});

test('rollAttack учитывает защиту и крит', () => {
  const rng = makeRng(123);
  const attacker = { damage: 20, critChance: 1, critDamage: 2 }; // гарант. крит
  const hit = rollAttack(rng, attacker, 5);
  assert.equal(hit.isCrit, true);
  // база 15, вариация 0.85–1.15, крит ×2 → 26..34
  assert.ok(hit.damage >= 25 && hit.damage <= 35, `получено ${hit.damage}`);

  const normal = rollAttack(makeRng(5), { damage: 10, critChance: 0 }, 20);
  assert.equal(normal.isCrit, false);
  assert.ok(normal.damage >= 1); // минимум 1 даже при защите выше урона
});

test('rollMobAttack не опускается ниже 1', () => {
  const dmg = rollMobAttack(makeRng(1), 3, 100);
  assert.equal(dmg, 1);
});

test('rollFlee растёт от ловкости', () => {
  // p=0.55 + agi*0.01; при rng=0 всегда успех
  assert.equal(rollFlee(() => 0, 10), true);
  // при rng≈1 всегда провал
  assert.equal(rollFlee(() => 0.99, 10), false);
});

test('effectiveStats суммирует бонусы экипировки', () => {
  const char = { str: 8, end: 6, agi: 5, critChance: 0.05, critDamage: 1.5 };
  const items = [
    { bonuses: { damage: 7, str: 1 } },
    { bonuses: { defense: 8, maxHp: 40 } },
    { bonuses: { critChance: 0.05, agi: 3 } },
  ];
  const s = effectiveStats(char, items);
  assert.equal(s.damage, 16 + 7); // str*2 + damage
  assert.equal(s.defense, 3 + 8);  // floor(end/2) + defense
  assert.equal(Math.round(s.critChance * 100), 10);
  assert.equal(s.maxHpBonus, 40);
});

test('expToNext использует кривую level*100', () => {
  assert.equal(expToNext(1), 100);
  assert.equal(expToNext(7), 700);
});
