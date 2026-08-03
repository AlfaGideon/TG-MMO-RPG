"""Запуск всех проверок: python3 tests/run_all.py"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUITES = ["test_engine.py", "test_pages.py", "test_transport.py", "test_access.py",
          "test_admin_sync.py", "test_shop_bag.py", "test_wiring.py",
          "test_economy.py", "test_gameplay.py", "test_items_magic.py",
          "test_worldgen.py", "test_cataclysm.py",
          "test_living_world.py", "test_social_world.py",
          "test_stash.py", "test_world_endgame.py",
          "test_factions.py", "test_dungeon.py",
          "test_party.py",
          "test_miniapp.py",
          "test_server_stash.py",
          "test_parity.py",
          "test_merchant.py",
          "test_server_world.py",
          "test_bugfixes.py",
          "test_ai_lore.py",
          "test_telegram_dedup.py",
          "test_admin_layout.py",
          "test_proxy.py",
          "test_bot_edit.py",
          "test_bot_runner.py",
          "test_admin_logs.py",
          "test_bot_ui.py",
          "test_progression.py", "test_ui_images.py"]

# Без этих пакетов серверные сценарии не падают, а ТИХО ПРОПУСКАЮТСЯ —
# зелёный прогон тогда ничего не доказывает про серверный стек.
SERVER_DEPS = ("sqlalchemy", "aiosqlite")


def check_server_deps():
    missing = []
    for pkg in SERVER_DEPS:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print("!" * 46)
        print("⚠️  ВНИМАНИЕ: не установлены " + ", ".join(missing) + ".")
        print("⚠️  Серверные тесты будут ПРОПУЩЕНЫ (это НЕ успех).")
        print("⚠️  Установи: pip install -r requirements.txt")
        print("!" * 46)
    return missing


def main():
    missing = check_server_deps()
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
    if missing:
        print("⚠️  Все доступные наборы зелёные, но серверные "
              "пропущены из-за отсутствия зависимостей!")
    print(f"✅ Все наборы пройдены ({len(SUITES)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
