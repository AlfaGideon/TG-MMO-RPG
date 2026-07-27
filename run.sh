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
python launch.py
