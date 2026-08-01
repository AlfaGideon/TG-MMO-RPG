"""Вкладка «Логи» в админке: страница, API, тихий /api/bot/status.

Проверяем:
* /api/bot/status (опрос панели каждые 5с) не попадает в буфер логов
  (фильтр на uvicorn.access) — консоль не спамится;
* GET /logs рендерится;
* GET /api/logs отдаёт записи; POST /api/logs/clear очищает буфер.

python3 tests/test_admin_logs.py
"""
import logging
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Тестовая БД — до импорта admin.main (он читает DATABASE_URL при импорте).
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + _tmp_db.name

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


def _have(*mods):
    import importlib.util
    return all(importlib.util.find_spec(m) for m in mods)


def test_quiet_status_filter():
    """Access-лог «GET /api/bot/status» не доходит до буфера логов."""
    from admin.logs import log_buffer
    import admin.main  # noqa: F401 — импорт ставит фильтр и буфер

    log_buffer.clear()
    access = logging.getLogger("uvicorn.access")
    # WARNING-уровень, чтобы запись прошла мимо уровня логгера в тестах.
    access.warning('127.0.0.1:1234 - "GET /api/bot/status HTTP/1.1" 200 OK')
    access.warning('127.0.0.1:1234 - "GET /settings HTTP/1.1" 200 OK')

    msgs = [r["message"] for r in log_buffer.snapshot()]
    check(any("/settings" in m for m in msgs),
          "обычный запрос панели попадает в лог")
    check(not any("/api/bot/status" in m for m in msgs),
          "опрос /api/bot/status отфильтрован")


def test_logs_page_and_api():
    """Страница /logs рендерится, API отдаёт и чистит записи."""
    from starlette.testclient import TestClient
    from admin.main import app

    with TestClient(app) as c:
        page = c.get("/logs")
        check(page.status_code == 200, "GET /logs → 200")
        check("Логи" in page.text, "страница содержит «Логи»")
        check("loadLogs" in page.text, "страница содержит автообновление")

        r = c.get("/api/logs")
        data = r.json()
        check(r.status_code == 200 and isinstance(data.get("records"), list),
              "GET /api/logs → список записей")

        r = c.get("/api/logs?level=ERROR")
        check(r.json()["records"] == [], "нет ERROR-записей → пустой список")

        # Ошибка попадает в буфер и исчезает после очистки.
        logging.getLogger("test.admin").error("test-error-for-clear")
        recs = c.get("/api/logs?level=ERROR").json()["records"]
        check(any("test-error-for-clear" in x["message"] for x in recs),
              "ERROR-запись попадает в буфер")

        r = c.post("/api/logs/clear")
        check(r.json().get("ok") is True, "POST /api/logs/clear → ok")
        recs = c.get("/api/logs?level=ERROR").json()["records"]
        check(not any("test-error-for-clear" in x["message"] for x in recs),
              "после очистки ERROR-записи нет")


def main():
    if not _have("sqlalchemy", "aiosqlite", "httpx", "fastapi", "aiogram"):
        print("⚠️  ПРОПУСК: нет серверных зависимостей (sqlalchemy/httpx/...)")
        return 0

    test_quiet_status_filter()
    test_logs_page_and_api()

    print()
    if FAILED:
        print("❌ Провалено: " + ", ".join(FAILED))
        return 1
    print("✅ Все проверки логов пройдены")
    return 0


if __name__ == "__main__":
    sys.exit(main())
