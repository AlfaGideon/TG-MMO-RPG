"""
Realtime event bus для связки бота и админ-панели.

Идея:
- бот при любом важном действии (движение, бой, регистрация, открытие портала, экономика)
  публикует событие в in-memory шину.
- админ-панель держит WebSocket /ws/live и отдаёт события живым обновлениям без перезагрузки страницы.
- Если WS не подключён, события копятся в небольшом ring-buffer (last 200) для первичной загрузки.

События:
  player_move: character_id, name, location_id, location_name, floor, x, y, is_vip
  player_joined: character_id, name, telegram_id, class, level
  player_levelup, battle_result, chest_opened, portal_opened, portal_closed, portal_tick
  auction_new, auction_sold, auction_expired, mob_respawn, economy_tick

Шина полностью in-memory, без Redis — достаточно для одного процесса админки.
Если админка перезапускается — буфер сбрасывается, клиенты переподключаются.

Публикация из бота: бот и админка могут жить в одном процессе (bot_runner), поэтому
шина общая через импорт. Если бот в отдельном процессе — события не дойдут, но
у нас один процесс через launch.py, так что работает.
"""
import asyncio
import json
import time
from collections import deque
from typing import Any, Dict, Set

MAX_HISTORY = 200

_history: deque = deque(maxlen=MAX_HISTORY)
_subscribers: Set[asyncio.Queue] = set()
_lock = asyncio.Lock()


async def publish(event_type: str, payload: Dict[str, Any]):
    """Публикует событие всем подписчикам. Потокобезопасно."""
    event = {
        "type": event_type,
        "payload": payload,
        "ts": time.time(),
        "id": int(time.time() * 1000),
    }
    _history.append(event)
    # Копируем список подписчиков, чтобы не держать lock во время put
    async with _lock:
        subs = list(_subscribers)
    for q in subs:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            # если клиент не успевает — пропускаем
            try:
                q.get_nowait()
                q.put_nowait(event)
            except Exception:
                pass
        except Exception:
            pass
    return event


def publish_sync(event_type: str, payload: Dict[str, Any]):
    """Синхронная версия для вызова из не-async контекстов (создаёт task)."""
    try:
        loop = asyncio.get_running_loop()
        if loop and loop.is_running():
            loop.create_task(publish(event_type, payload))
        else:
            # fallback — просто в историю
            _history.append({
                "type": event_type,
                "payload": payload,
                "ts": time.time(),
                "id": int(time.time() * 1000),
            })
    except RuntimeError:
        _history.append({
            "type": event_type,
            "payload": payload,
            "ts": time.time(),
            "id": int(time.time() * 1000),
        })


async def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    async with _lock:
        _subscribers.add(q)
    return q


async def unsubscribe(q: asyncio.Queue):
    async with _lock:
        _subscribers.discard(q)


def get_history(limit: int = 50):
    return list(_history)[-limit:]


def clear():
    _history.clear()
