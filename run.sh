#!/bin/bash
echo "🌑 Shadow Lands — запуск..."

if [ ! -d "venv" ]; then
    echo "Создаю виртуальное окружение..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "Устанавливаю зависимости..."
pip install -q -r requirements.txt

echo "Запускаю сервер..."

# Открываем админку в браузере, как только сервер ответит (SL_NO_BROWSER=1 — выключить).
SL_STARTING_FLAG="$(mktemp -t shadowlands_starting.XXXXXX)"
trap 'rm -f "$SL_STARTING_FLAG"' EXIT
python tools/open_admin.py --stop-file "$SL_STARTING_FLAG" &

python launch.py
