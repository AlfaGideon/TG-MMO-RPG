"""Проверка сборки URL транспорта: python3 tests/test_transport.py"""
import os
import sys
import types
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Заглушка модуля js (в браузере его даёт Pyodide).
fake_js = types.ModuleType("js")
fake_js.encodeURIComponent = lambda s: urllib.parse.quote(str(s), safe="")
sys.modules.setdefault("js", fake_js)

from webapp.transport import PRESETS, Transport  # noqa: E402

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


def main():
    print("\n— Режим direct —")
    t = Transport({"proxy_mode": "direct"})
    url = t.build("123:ABC", "getMe")
    check(url == "https://api.telegram.org/bot123:ABC/getMe", url)
    url = t.build("123:ABC", "getUpdates", "offset=5&timeout=25")
    check(url.endswith("/getUpdates?offset=5&timeout=25"), url)

    print("\n— Пресеты прокси —")
    for name, prefix in PRESETS.items():
        if not prefix:
            continue
        t = Transport({"proxy_mode": name})
        url = t.build("T", "getMe")
        ok = url.startswith(prefix) and "api.telegram.org" in urllib.parse.unquote(url)
        check(ok, f"{name}: {url[:70]}…")

    print("\n— Свой прокси —")
    t = Transport({"proxy_mode": "custom", "proxy_url": "https://my.relay/?url="})
    url = t.build("T", "sendMessage", "chat_id=1&text=hi")
    check(url.startswith("https://my.relay/?url="), "префикс подставлен")
    check("api.telegram.org" in urllib.parse.unquote(url), "цель закодирована внутри")
    check("%3F" in url or "%3f" in url, "query экранирован")

    print("\n— Фолбэк на неизвестный режим —")
    t = Transport({"proxy_mode": "нет-такого"})
    check(t.build("T", "getMe").startswith("https://api.telegram.org"), "падает в direct")

    print("\n" + "=" * 46)
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}")
        for f in FAILED:
            print("   -", f)
        return 1
    print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
