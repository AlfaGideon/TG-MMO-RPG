// Детерминированный ГПСЧ (mulberry32) + игровые хелперы.
// Чистый модоль без импорта sdk — юнит-тестируется локально через node --test.

export function makeRng(seed) {
  let a = seed >>> 0;
  return function rng() {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function intBetween(rng, min, max) {
  return min + Math.floor(rng() * (max - min + 1));
}

export function chance(rng, p) {
  return rng() < p;
}

export function pick(rng, arr) {
  return arr[Math.floor(rng() * arr.length)];
}

// Seed из времени + соли, когда детерминизм не нужен (боевой вызов).
export function randomSeed(salt = 0) {
  return (Date.now() ^ Math.floor(Math.random() * 0xffffffff) ^ (salt * 2654435761)) >>> 0;
}
