// Заглушка для inline-кнопок: подтверждаем нажатие. Web App-кнопки открываются
// платформой сами и сюда не приходят.
import { api } from 'sdk';

export default async function (update) {
  const cq = update.callback_query;
  await api.answerCallbackQuery({
    callback_query_id: cq.id,
    text: 'Откройте Mini App кнопкой ниже.',
  });
}
