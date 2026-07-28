"""Точка входа Python-приложения в браузере."""
import asyncio

from js import window

from webapp.app import App

app = App()
window.__app = app


def main():
    asyncio.ensure_future(app.boot())


main()
