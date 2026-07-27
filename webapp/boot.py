"""Точка входа Python-приложения в браузере."""
import asyncio

from webapp.app import App

app = App()


def main():
    asyncio.ensure_future(app.boot())


main()
