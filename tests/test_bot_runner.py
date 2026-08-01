"""BotRunner: защита от двойного запуска и остановка при конфликте getUpdates.

Регрессия: два параллельных start() (двойной клик «Запустить бота») создавали
два polling-цикла → TelegramConflictError «terminated by other getUpdates
request», и бот вечно дрался сам с собой. Теперь start/stop сериализованы
блокировкой, а повторные конфликты останавливают polling с понятным
сообщением в панели.

python3 tests/test_bot_runner.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


def _have(*mods):
    import importlib.util
    return all(importlib.util.find_spec(m) for m in mods)


async def _stub_loops(r):
    """Заменяем сетевые/БД-циклы заглушками — тест не ходит в сеть и БД."""
    async def fake_poll():
        await asyncio.sleep(30)

    async def fake_noop():
        pass

    r._poll = fake_poll
    r._notify_resume_on_start = fake_noop
    r._cleanup_after_restart = fake_noop
    r._portal_sweep_loop = fake_noop
    r._spawn_tick_loop = fake_noop


def test_double_start_locked():
    """Два одновременных start() → работает только один polling-цикл."""

    async def run():
        from bot.runner import BotRunner
        r = BotRunner()
        await _stub_loops(r)
        ok1, ok2 = await asyncio.gather(
            r.start("123456789:ABCdefGHIjklMNOpqrsTUVwxyz", ""),
            r.start("123456789:ABCdefGHIjklMNOpqrsTUVwxyz", ""),
        )
        check(ok1 is True, "первый start() запустил бота")
        check(ok2 is False, "второй параллельный start() отклонён")
        check(r.is_running(), "бот работает (один polling-цикл)")
        check(await r.stop() is True, "stop() останавливает бота")
        check(not r.is_running(), "после stop() бот не работает")

    asyncio.run(run())


def test_conflict_stops_bot_with_message():
    """Повторный TelegramConflictError → понятное сообщение + остановка."""

    async def run():
        from aiogram.exceptions import TelegramConflictError
        from bot.runner import BotRunner, CONFLICT_MESSAGE
        r = BotRunner()
        r._running = True
        r._task = asyncio.create_task(asyncio.sleep(30))
        exc = TelegramConflictError(
            method=None, message="terminated by other getUpdates request")

        r._note_conflict(exc)
        await asyncio.sleep(0.2)
        check(r.last_error == CONFLICT_MESSAGE,
              "после первого конфликта панель показывает причину")

        r._note_conflict(exc)  # второй конфликт — чужой экземпляр жив
        await asyncio.sleep(3.0)  # воркер проверяет через 2.5с
        check("Бот остановлен" in (r.last_error or ""),
              "повторный конфликт → бот остановлен с объяснением")
        check(not r.is_running(), "после конфликта polling не работает")

    asyncio.run(run())


def test_single_conflict_recovered():
    """Единичный конфликт (чужой экземпляр уже умер) не останавливает бота."""

    async def run():
        from aiogram.exceptions import TelegramConflictError
        from bot.runner import BotRunner
        r = BotRunner()
        r.last_error = "прежняя ошибка"
        exc = TelegramConflictError(
            method=None, message="terminated by other getUpdates request")
        r._note_conflict(exc)
        await asyncio.sleep(3.0)
        check(r.last_error == "прежняя ошибка",
              "единичный конфликт → прежняя ошибка восстановлена")

    asyncio.run(run())


def main():
    if not _have("aiogram", "sqlalchemy"):
        print("⚠️  ПРОПУСК: нет aiogram/sqlalchemy (серверные зависимости)")
        return 0

    test_double_start_locked()
    test_conflict_stops_bot_with_message()
    test_single_conflict_recovered()

    print()
    if FAILED:
        print("❌ Провалено: " + ", ".join(FAILED))
        return 1
    print("✅ Все проверки BotRunner пройдены")
    return 0


if __name__ == "__main__":
    sys.exit(main())
