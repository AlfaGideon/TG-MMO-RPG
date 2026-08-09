import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import init_db


@pytest.fixture(scope="session", autouse=True)
async def init_test_database():
    """Автоматически инициализирует структуру БД перед прогоном тестов."""
    await init_db()
