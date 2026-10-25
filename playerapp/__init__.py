"""Игровое мобильное приложение Shadow Lands (стек B, серверная часть).

Отдельный от админки API для игроков: вход по коду из Telegram-бота или
по подписанным initData Mini App, игровые действия поверх того же core/*,
что и сам бот. Бот и приложение работают с ОДНОЙ базой — прогресс общий:
герой, над которым игрок играет в Telegram, доступен в APK и наоборот.

Размещение:
  playerapp/models.py   — таблицы кодов входа и Bearer-сессий
  playerapp/auth.py     — коды, токены, проверка подписи Telegram
  playerapp/service.py  — игровая логика (профиль, карта, движение, бой…)
  playerapp/api.py      — FastAPI-роутер /api/player/* и отдача SPA
  playerapp/static/     — мобильный веб-клиент (он же Telegram Mini App)
"""
