"""Команда /app: вход в мобильное приложение Shadow Lands.

Игрок получает:
  * одноразовый код для входа в standalone APK (вводится на экране входа);
  * кнопку Telegram Mini App — тот же клиент внутри Telegram, вход без
    кода по подписанным initData;
  * ссылку на свежий APK в релизах GitHub.

Бот, API и приложение работают с одной БД, поэтому прогресс общим:
герой, которым играют здесь, доступен в приложении и наоборот.
"""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message,
    ReplyKeyboardMarkup, WebAppInfo,
)

from core.database import async_session
from core.settings_store import PANEL_URL_KEY, get_setting
from playerapp.auth import issue_code

router = Router()

RELEASES_URL = "https://github.com/AlfaGideon/TG-MMO-RPG/releases/latest"


@router.message(Command("app"))
async def cmd_app(message: Message):
    async with async_session() as session:
        code = await issue_code(session, message.from_user.id)
        panel_url = (await get_setting(PANEL_URL_KEY)).rstrip("/")

    lines = [
        "📱 <b>Shadow Lands — приложение игрока</b>",
        "",
        "Один герой — в Telegram и в приложении: прогресс, инвентарь и "
        "уровни общие, всё хранится на сервере.",
        "",
        f"🔑 <b>Код для входа в APK:</b> <code>{code}</code>",
        "<i>Код одноразовый, действует 10 минут. Запросить новый можно "
        "в любой момент повторной командой /app.</i>",
    ]
    builder = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬇️ Скачать APK", url=RELEASES_URL)],
    ])

    if panel_url:
        # Mini App-кнопка возможна только на обычной клавиатуре (ограничение
        # Telegram: inline web_app тоже поддерживается, но в личных чатах
        # надёжнее reply-клавиатура).
        player_url = f"{panel_url}/player/"
        web_app = WebAppInfo(url=player_url)
        reply_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(
                text="🎮 Открыть Mini App", web_app=web_app
            )]],
            resize_keyboard=True,
        )
        lines += [
            "",
            "Нажми кнопку ниже, чтобы играть прямо в Telegram.",
            "",
            "📲 <b>В приложении на телефоне:</b> если игра не открылась "
            "сама, открой меню «Адрес сервера» и вставь этот адрес "
            "(путь допишется автоматически):",
            f"<code>{panel_url}</code>",
        ]
        await message.answer(
            "\n".join(lines), reply_markup=builder, parse_mode="HTML"
        )
        await message.answer(
            "🎮 Или открой Mini App кнопкой ниже 👇", reply_markup=reply_kb
        )
    else:
        lines += [
            "",
            "⚠️ Сервер с игровым API сейчас не запущен, поэтому Mini App "
            "недоступна. Код для APK сработает, когда сервер поднимется "
            "(адрес настраивается в переменной PUBLIC_URL или через туннель).",
        ]
        await message.answer(
            "\n".join(lines), reply_markup=builder, parse_mode="HTML"
        )
