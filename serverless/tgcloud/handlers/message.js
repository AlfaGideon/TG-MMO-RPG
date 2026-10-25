// Обработчик обычных сообщений и команд бота.
import { api } from 'sdk';
import { getOrCreateUser, getCharacterForTgId, createCharacter } from '../lib/character.js';
import { ensureWorld } from '../lib/world.js';
import { MINI_APP_URL, BOT_USERNAME } from '../lib/config.js';

function appKeyboard() {
  return {
    inline_keyboard: [[
      { text: '🎮 Открыть Shadow Lands', web_app: { url: MINI_APP_URL } },
      { text: '🔗 Ссылка', url: `https://t.me/${BOT_USERNAME}?startapp=enter` },
    ]],
  };
}

const HELP = [
  'Shadow Lands — команды:',
  '/start — создать героя и войти в мир',
  '/app — открыть Mini App с игрой',
  '/help — эта справка',
  '',
  'Прогресс общий: всё, что вы делаете в Mini App, сохраняется в облаке Telegram.',
].join('\n');

export default async function (update) {
  const msg = update.message;
  const chatId = msg.chat.id;
  const text = msg.text ?? '';
  const tgUser = msg.from;
  const lang = tgUser.language_code === 'ru' ? 'ru' : 'en';

  if (text.startsWith('/help')) {
    await api.sendMessage({ chat_id: chatId, text: HELP });
    return;
  }

  if (text.startsWith('/start') || text.startsWith('/app')) {
    await ensureWorld();
    const user = await getOrCreateUser(tgUser, lang);
    const pair = await getCharacterForTgId(tgUser.id);
    let greeting;
    if (!pair.character) {
      const character = await createCharacter(user, tgUser.first_name || 'Странник', 'warrior');
      greeting = [
        `Добро пожаловать в Shadow Lands, ${character.name}.`,
        'Вы — Воин у лагерного костра в Сумеречных руинах.',
        'Откройте Mini App, чтобы выйти на карту и сразиться с порождениями Теней.',
      ].join('\n');
    } else {
      greeting = `С возвращением, ${pair.character.name}. Уровень ${pair.character.level}, HP ${pair.character.hp}/${pair.character.maxHp}.`;
    }
    await api.sendMessage({
      chat_id: chatId,
      text: `${greeting}\n\nКнопка ниже откроет игру внутри Telegram — отдельный сервер больше не нужен.`,
      reply_markup: appKeyboard(),
    });
    return;
  }

  await api.sendMessage({
    chat_id: chatId,
    text: 'Я игровой бот Shadow Lands. Отправьте /app, чтобы открыть игру, или /help для справки.',
  });
}
