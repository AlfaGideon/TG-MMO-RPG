// Константы проекта.
// MINI_APP_URL подставляется ПОСЛЕ первого `tgcloud push` — CLI печатает адрес
// вида https://app1234567890.tgcloud.ai/ . Без него кнопка Web App в /start не
// сможет открыть мини-апп по абсолютному URL (требование Bot API).
export const MINI_APP_URL = 'https://APP_ID.tgcloud.ai/';

// Имя бота для deep-link (используется в /start и APK-лаунчером): t.me/<username>
export const BOT_USERNAME = 'Shadow_Land_bot';

// Игровые константы
export const GAME = {
  START_GOLD: { bronze: 0, silver: 0, gold: 0 },
  START_HP: 100,
  START_MP: 30,
  RESPAWN_HP_RATIO: 0.5,      // доля HP после поражения
  REST_HP_RATIO: 0.35,        // сколько макс. HP восстанавливает отдых у костра
  REST_MP_RATIO: 0.5,
  FLEE_BASE_CHANCE: 0.55,
  FLEE_HP_PENALTY: 0.1,       // урон при провале побега (доля макс. HP моба)
  DEATH_BRONZE_LOSS: 0.1,     // теряется 10% бронзы при поражении
  EXP_CURVE: (level) => level * 100, // опыта до следующего уровня
  STAT_POINTS_PER_LEVEL: 3,
  MOB_RESPAWN_SEC: 120,
  CHEST_RESPAWN_SEC: 300,
};

// Стартовые классы персонажа
export const CLASSES = {
  warrior: {
    key: 'warrior', name: 'Воин',
    str: 8, agi: 5, int: 3, end: 7, luck: 4,
    critChance: 0.05, critDamage: 1.5,
    maxHp: 120, maxMp: 20,
  },
  rogue: {
    key: 'rogue', name: 'Разбойник',
    str: 5, agi: 9, int: 4, end: 5, luck: 7,
    critChance: 0.15, critDamage: 1.8,
    maxHp: 95, maxMp: 30,
  },
  mage: {
    key: 'mage', name: 'Маг',
    str: 3, agi: 5, int: 10, end: 4, luck: 5,
    critChance: 0.08, critDamage: 1.6,
    maxHp: 80, maxMp: 60,
  },
};
