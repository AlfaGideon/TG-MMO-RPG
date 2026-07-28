"""Запуск всех проверок: python3 tests/run_all.py"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUITES = ["test_engine.py", "test_pages.py", "test_transport.py", "test_access.py",
          "test_admin_sync.py", "test_shop_bag.py", "test_wiring.py",
          "test_gameplay.py", "test_items_magic.py"]


def main():
    failed = []
    for name in SUITES:
        print(f"\n{'=' * 46}\n▶ {name}\n{'=' * 46}")
        code = subprocess.call([sys.executable, os.path.join(HERE, name)])
        if code:
            failed.append(name)
    print(f"\n{'=' * 46}")
    if failed:
        print("❌ Провалены наборы: " + ", ".join(failed))
        return 1
    print(f"✅ Все наборы пройдены ({len(SUITES)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
