"""Живой таймер для браузерной панели: работает через js.setInterval,

а не через встроенные <script>, которые не запускаются при innerHTML.
Это исправляет «таймеры всё ещё не живые» из world_cataclysms.py.
"""
from js import setInterval, clearInterval, document
from pyodide.ffi import create_proxy

_timers = []


def start_timer(interval_ms=1000, selector=".cata-timer[data-until]",
                 formatter=None):
    """Запускает таймер, который каждую секунду обновляет DOM-элементы.

    Использует чистый Python + `js.setInterval`, без встроенных
    `<script>`-тегов, которые не работают с `node.innerHTML`.
    """

    def tick(*_):
        nodes = document.querySelectorAll(selector)
        for i in range(nodes.length):
            el = nodes.item(i)
            if el is None:
                continue
            until_str = el.getAttribute("data-until")
            if not until_str:
                continue
            try:
                until = int(until_str)
            except (ValueError, TypeError):
                continue
            import time
            left = until - int(time.time())
            if left <= 0:
                el.textContent = "🕊 стихает"
                continue
            if formatter is not None:
                try:
                    el.textContent = formatter(left)
                except Exception:
                    pass
            else:
                h = left // 3600
                m = (left % 3600) // 60
                s = left % 60
                el.textContent = (f"⏳ " + (f"{h}ч " if h else "")
                                  + f"{m}м " + f"{s}с")

    proxy = create_proxy(tick)
    _timers.append(proxy)
    interval_id = setInterval(proxy, interval_ms)
    tick()  # первый вызов сразу
    return interval_id


def stop_timer(interval_id):
    clearInterval(interval_id)


def start_clock(interval_ms=1000, time_id="worldTime", date_id="worldDate"):
    """Красивые тематические часы в боковой панели (Shadow Lands).

    Обновляются каждую секунду через js.setInterval. Формат:
    время в стиле «23:47» + дата «30.07.2026». Не мешает интерфейсу,
    живёт в подвале сайдбара.
    """
    def tick(*_):
        from js import Date
        now = Date.new()
        time_node = document.querySelector(f"#{time_id}")
        date_node = document.querySelector(f"#{date_id}")
        if time_node is not None:
            time_str = now.toLocaleTimeString("ru-RU", {hour: "2-digit", minute: "2-digit", second: "2-digit"})
            time_node.textContent = time_str
        if date_node is not None:
            date_str = now.toLocaleDateString("ru-RU", {day: "2-digit", month: "2-digit", year: "numeric"})
            date_node.textContent = date_str

    proxy = create_proxy(tick)
    _timers.append(proxy)
    interval_id = setInterval(proxy, interval_ms)
    tick()
    return interval_id


def default_cataclysm_formatter(left):
    h = left // 3600
    m = (left % 3600) // 60
    s = left % 60
    return f"⏳ {(f'{h}ч ' if h else '')}{m}м {s}с"
