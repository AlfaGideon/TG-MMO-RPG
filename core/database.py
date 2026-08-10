import os
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/game.db")

if DATABASE_URL.startswith("sqlite") and "/data/" in DATABASE_URL:
    os.makedirs("./data", exist_ok=True)

# Fix Render.com postgres:// prefix
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
if DATABASE_URL.startswith("postgresql://") and "asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

_is_sqlite = DATABASE_URL.startswith("sqlite")
_engine_kwargs = {"echo": False}
if _is_sqlite:
    # Не зависать на стандартные 5 секунд при настоящем конфликте записи.
    # WAL ниже позволяет чтениям и записи идти параллельно; timeout остаётся
    # страховкой только для двух одновременных writers.
    _engine_kwargs["connect_args"] = {"timeout": 3.0}

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)


if _is_sqlite:
    @event.listens_for(engine.sync_engine, "connect")
    def _configure_sqlite(dbapi_connection, _connection_record):
        """Режим SQLite для живого бота: без read/write блокировок на 5 секунд."""
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=3000")
        finally:
            cursor.close()


async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


async def init_db():
    # На SQLite один create_all не чинит старые базы (не добавляет новые
    # колонки в существующие таблицы) — поэтому все точки входа гоняют
    # полный раннер миграций. Ленивый импорт: core.migrations тянет
    # core.models, а тот — этот модуль.
    if DATABASE_URL.startswith("sqlite"):
        from core.migrations import run_migrations
        await run_migrations()
        return
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
