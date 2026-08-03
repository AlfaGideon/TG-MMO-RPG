"""Регрессии живой админ-панели: WebSocket и пагинация без cartesian product.

python3 tests/test_admin_realtime.py
"""
import inspect
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FAILED = []


def check(condition, label):
    print(("  ✅ " if condition else "  ❌ ") + label)
    if not condition:
        FAILED.append(label)


def _have(*modules):
    import importlib.util
    return all(importlib.util.find_spec(module) for module in modules)


def main():
    if not _have("fastapi", "sqlalchemy"):
        print("⚠️  ПРОПУСК: нужны fastapi и sqlalchemy")
        return 0

    from fastapi import WebSocket
    from admin.main import app, editor_instances, items, players, ws_live

    print("\n— Живая панель —")
    websocket_param = inspect.signature(ws_live).parameters["websocket"]
    check(websocket_param.annotation is WebSocket,
          "WebSocket аннотирован — FastAPI принимает handshake, а не отвечает 403")
    routes = {getattr(route, "path", "") for route in app.routes}
    check("/ws/live" in routes, "маршрут live-канала зарегистрирован")
    if _have("httpx2"):
        from fastapi.testclient import TestClient
        try:
            with TestClient(app) as client:
                with client.websocket_connect("/ws/live"):
                    check(True, "WebSocket проходит реальный handshake")
        except Exception as exc:  # noqa: BLE001
            check(False, f"WebSocket handshake → {type(exc).__name__}: {exc}")
    else:
        print("  ⚠️  ПРОПУСК: handshake (нет httpx2)")

    print("\n— Пагинация без декартова произведения —")
    sources = "\n".join(inspect.getsource(fn) for fn in (players, items, editor_instances))
    check("select(func.count(Character.id)).select_from(base_query.subquery())" not in sources,
          "список игроков не присоединяет characters второй раз")
    check("select(func.count(Item.id)).select_from(base_query.subquery())" not in sources,
          "список предметов не присоединяет items второй раз")
    check("select(func.count(ItemInstance.id)).select_from(base_query.subquery())" not in sources,
          "реестр экземпляров не присоединяет item_instances второй раз")
    check(sources.count("select(func.count()).select_from(base_query.order_by(None).subquery())") == 3,
          "все три счётчика считают строки собственных подзапросов")

    print()
    if FAILED:
        print("❌ Провалено: " + ", ".join(FAILED))
        return 1
    print("✅ Live-канал и счётчики панели в порядке")
    return 0


if __name__ == "__main__":
    sys.exit(main())
