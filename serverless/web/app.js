/* Shadow Lands — клиент Mini App на Telegram Serverless.
   Авторизация не нужна: платформа сама подписывает и проверяет initData,
   endpoints получают пользователя из ctx.initData.user. */
'use strict';

const tg = window.Telegram?.WebApp;
const $ = (id) => document.getElementById(id);

const CLASS_NAMES = { warrior: 'Воин', rogue: 'Разбойник', mage: 'Маг' };
const RARITY_NAMES = {
  common: 'Обычный', uncommon: 'Необычный', rare: 'Редкий',
  epic: 'Эпический', legendary: 'Легендарный',
};

let state = null;
let busy = false;

// Обёртка над callback-API Serverless.call.
function call(name, input = {}) {
  return new Promise((resolve, reject) => {
    tg.Serverless.call(name, input, (err, result) => {
      if (err) reject(err);
      else resolve(result);
    });
  });
}

function toast(text, kind = 'ok') {
  const el = $('toast');
  el.textContent = text;
  el.className = `toast show ${kind}`;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.className = 'toast'; }, 2600);
}

async function action(name, input) {
  if (busy) return null;
  busy = true;
  try {
    const next = await call(name, input);
    if (next) state = next;
    render();
    (next?.messages || []).forEach((m) => toast(m));
    if (next?.battleResult?.status === 'won') toast('Победа!', 'ok');
    if (next?.battleResult?.status === 'lost') toast('Вы пали… возрождение у костра', 'err');
    if (next?.fleeResult && next.fleeResult.escaped) toast('Вы сбежали из боя');
    return next;
  } catch (err) {
    toast(err.message || 'Ошибка соединения с облаком', 'err');
    return null;
  } finally {
    busy = false;
  }
}

// ── Рендер ───────────────────────────────────────────────────────────────────
function pct(a, b) { return b > 0 ? Math.max(0, Math.min(100, (a / b) * 100)) : 0; }

function statBox(k, v) {
  return `<div class="stat-box"><div class="k">${k}</div><div class="v">${v}</div></div>`;
}

function renderProfile() {
  const c = state.character;
  $('heroName').textContent = c.name;
  $('heroLevel').textContent = `ур. ${c.level}`;
  $('hpText').textContent = `${c.hp}/${c.maxHp} HP`;
  $('hpFill').style.width = `${pct(c.hp, c.maxHp)}%`;

  $('profileName').textContent = c.name;
  $('profileClass').textContent = CLASS_NAMES[c.classKey] || c.classKey;
  $('statGrid').innerHTML = [
    statBox('Сила', c.str), statBox('Ловкость', c.agi),
    statBox('Интеллект', c.int), statBox('Выносливость', c.end),
    statBox('Удача', c.luck), statBox('Очки', c.statPoints),
  ].join('');
  const need = c.level * 100;
  $('xpText').textContent = `${c.exp} / ${need}`;
  $('xpFill').style.width = `${pct(c.exp, need)}%`;

  $('walletGrid').innerHTML = [
    statBox('Бронза', c.bronze), statBox('Серебро', c.silver),
    statBox('Золото', c.gold), statBox('Мана', `${c.mp}/${c.maxMp}`),
  ].join('');

  const s = state.stats;
  $('combatGrid').innerHTML = [
    statBox('Урон', s.damage), statBox('Защита', s.defense),
    statBox('Крит', `${Math.round(s.critChance * 100)}%`),
    statBox('Множитель', `×${s.critDamage.toFixed(1)}`),
  ].join('');
}

function renderMap() {
  const cell = state.cell;
  $('coords').textContent = `${cell.x}, ${cell.y}`;
  $('locName').textContent = cell.name || 'Сумеречные руины';
  $('locDesc').textContent = cell.description || 'Мшистые камни и пыль.';

  const tags = [];
  if (cell.campfire) tags.push('<span class="tag">🔥 Костёр</span>');
  if (cell.chest) tags.push('<span class="tag">🧰 Сундук</span>');
  if (cell.npc) tags.push(`<span class="tag">🧑‍🌾 ${cell.npc}</span>`);
  if (cell.mob) tags.push(`<span class="tag">👹 ${cell.mob.name} ${cell.mob.level} ур.</span>`);
  $('cellTags').innerHTML = tags.join('');

  // D-pad: блокируем непроходимое и неразведанное.
  document.querySelectorAll('.dpad-btn').forEach((btn) => {
    const n = state.neighbors.find((x) => x.dir === btn.dataset.dir);
    btn.disabled = !n || !n.passable;
    btn.title = n ? n.label : '';
  });

  // Моб на клетке.
  const hasMob = !!cell.mob && !state.battle;
  $('mobCard').hidden = !hasMob && !state.battle;
  if (hasMob) {
    $('mobInfo').innerHTML = `
      <div class="mob-row">
        <div><div class="name">${cell.mob.isBoss ? '💀 ' : '👹 '}${cell.mob.name}</div>
        <div class="meta">Уровень ${cell.mob.level} · HP ${cell.mob.hp}/${cell.mob.maxHp}</div></div>
      </div>`;
    $('btnFight').dataset.spawn = cell.mob.spawnId;
  }
  $('btnInspect').hidden = !cell.chest && !cell.description;
  $('btnRest').hidden = !cell.campfire;

  // Активный бой.
  const b = state.battle;
  $('battleCard').hidden = !b;
  if (b) {
    $('battleMobName').textContent = b.mob.name;
    $('mobHpText').textContent = `${b.mobHp}/${b.mob.maxHp} HP · раунд ${b.round}`;
    $('mobHpFill').style.width = `${pct(b.mobHp, b.mob.maxHp)}%`;
    $('battleLog').innerHTML = (b.log || []).map((line) => `<p>${line}</p>`).join('');
    const log = $('battleLog');
    log.scrollTop = log.scrollHeight;
  }
}

function renderInventory() {
  const list = $('itemList');
  if (!state.inventory.length) {
    list.innerHTML = '<p class="empty">Пока пусто. Победите врага или загляните в сундук.</p>';
    return;
  }
  list.innerHTML = state.inventory.map((row) => {
    const it = row.item;
    const bonus = Object.entries(it.bonuses || {})
      .map(([k, v]) => `${k} +${v}`).join(', ');
    let actionBtn;
    if (row.equipped) {
      actionBtn = `<button class="btn" data-act="unequip" data-id="${row.id}">Снять</button>`;
    } else if (it.type === 'potion') {
      actionBtn = `<button class="btn primary" data-act="useItem" data-id="${row.id}">Выпить</button>`;
    } else if (['weapon', 'armor', 'misc'].includes(it.type)) {
      actionBtn = `<button class="btn primary" data-act="equip" data-id="${row.id}">Надеть</button>`;
    } else {
      actionBtn = '';
    }
    return `<div class="item-row">
      <div class="info">
        <div class="name rarity-${it.rarity}">${it.name} ${row.quantity > 1 ? `×${row.quantity}` : ''}</div>
        <div class="sub">${RARITY_NAMES[it.rarity] || it.rarity} · ${it.description}${bonus ? ` · ${bonus}` : ''}</div>
      </div>
      ${actionBtn}
    </div>`;
  }).join('');
}

function render() {
  if (!state) return;
  renderProfile();
  renderMap();
  renderInventory();
}

// ── Навигация и события ──────────────────────────────────────────────────────
function switchTab(tab) {
  document.querySelectorAll('.nav-btn').forEach((b) =>
    b.classList.toggle('active', b.dataset.tab === tab));
  ['profile', 'map', 'inventory'].forEach((t) => {
    $(`tab-${t}`).hidden = t !== tab;
  });
}

document.querySelectorAll('.nav-btn').forEach((b) =>
  b.addEventListener('click', () => switchTab(b.dataset.tab)));

document.querySelectorAll('.dpad-btn').forEach((b) =>
  b.addEventListener('click', () => action('move', { dir: b.dataset.dir })));

$('btnFight').addEventListener('click', () =>
  action('battleStart', { spawnId: Number($('btnFight').dataset.spawn) }));
$('btnAttack').addEventListener('click', () => action('battleAttack'));
$('btnFlee').addEventListener('click', () => action('battleFlee'));
$('btnInspect').addEventListener('click', () => action('inspect'));
$('btnRest').addEventListener('click', () => action('rest'));

$('itemList').addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-act]');
  if (!btn) return;
  action(btn.dataset.act, { inventoryId: Number(btn.dataset.id) });
});

// ── Старт ────────────────────────────────────────────────────────────────────
async function boot() {
  if (!tg || !tg.initData) {
    $('loginText').textContent = 'Приложение открыто вне Telegram.';
    $('loginStatus').hidden = false;
    $('loginStatus').textContent =
      'Откройте бота в Telegram и нажмите «Открыть Shadow Lands» — игровые endpoints доступны только из Mini App.';
    return;
  }
  tg.ready();
  tg.expand();
  try {
    state = await call('getProfile');
    $('loginScreen').hidden = true;
    $('gameShell').hidden = false;
    render();
  } catch (err) {
    $('loginText').textContent = 'Не удалось войти в мир.';
    $('loginStatus').hidden = false;
    $('loginStatus').textContent = err.message || 'Платформа отклонила запрос (401).';
  }
}

boot();
