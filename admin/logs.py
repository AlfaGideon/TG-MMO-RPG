"""Консольные логи сервера — кольцевой буфер для вкладки «Логи» в админке.

Перехватываем записи стандартного logging (aiogram, uvicorn, приложение) и
храним последние MAX_RECORDS в памяти, чтобы показывать их в веб-панели
(/logs). Сама консоль продолжает работать как раньше.
"""
import logging
import threading
from collections import deque
from datetime import datetime

MAX_RECORDS = 2000


class RingBufferHandler(logging.Handler):
    """Handler, который держит последние N записей в памяти."""

    def __init__(self, maxlen: int = MAX_RECORDS):
        super().__init__(level=logging.NOTSET)
        self._records = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "time": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
                "level": record.levelname,
                "logger": record.name,
                "message": self.format(record),
            }
            with self._lock:
                self._records.append(entry)
        except Exception:
            pass

    def snapshot(self, level: str = "", limit: int = 500) -> list:
        """Последние записи, новые сверху.

        level — минимальный уровень записи (ERROR / WARNING / INFO / DEBUG);
        пустая строка — все уровни.
        """
        ranks = {
            "ERROR": logging.ERROR,
            "WARNING": logging.WARNING,
            "INFO": logging.INFO,
            "DEBUG": logging.DEBUG,
        }
        need = ranks.get((level or "").upper())
        with self._lock:
            items = list(self._records)
        if need:
            items = [r for r in items
                     if logging._nameToLevel.get(r["level"], 0) >= need]
        return list(reversed(items[-limit:]))

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


log_buffer = RingBufferHandler()
log_buffer.setFormatter(logging.Formatter("%(message)s"))

# Логгеры, чьи записи нужны в панели. uvicorn.* по умолчанию не
# распространяют записи в root, поэтому вешаем handler на каждый напрямую.
_CAPTURE_LOGGERS = (
    "",                              # root: приложение, aiogram и т.п.
    "aiogram", "aiogram.event", "aiogram.dispatcher",
    "uvicorn", "uvicorn.error", "uvicorn.access",
    "aiohttp", "sqlalchemy", "launcher",
)


def install_log_buffer() -> None:
    """Подключает буфер к логгерам. Безопасно вызывать повторно."""
    root = logging.getLogger()
    if log_buffer in root.handlers:
        return
    # Чтобы в панели были видны и INFO-записи даже при прямом запуске
    # «uvicorn admin.main:app» (без launch.py и basicConfig(INFO)).
    if root.level > logging.INFO:
        root.setLevel(logging.INFO)
    
    # Достаточно повесить на root, так как большинство логгеров пробрасывают
    # записи вверх (propagate=True). Для uvicorn проверяем отдельно.
    root.addHandler(log_buffer)
    
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        l = logging.getLogger(name)
        if not l.propagate and log_buffer not in l.handlers:
            l.addHandler(log_buffer)
