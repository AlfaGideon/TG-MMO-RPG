"""Бэкенд хранилища: localStorage браузера."""


class LocalStorage:
    def __init__(self):
        from js import window
        self._ls = window.localStorage

    def get(self, key):
        v = self._ls.getItem(key)
        return None if v is None else str(v)

    def set(self, key, value):
        self._ls.setItem(key, value)

    def clear(self, key):
        self._ls.removeItem(key)


class MemoryStorage:
    """Фолбэк для тестов вне браузера."""
    def __init__(self):
        self._d = {}

    def get(self, key):
        return self._d.get(key)

    def set(self, key, value):
        self._d[key] = value

    def clear(self, key):
        self._d.pop(key, None)
