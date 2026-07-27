#!/bin/bash
set -e

cd "$(dirname "$0")"

# Activate venv
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Create data dir
mkdir -p data

echo "🌑 Shadow Lands — запуск единого сервера"
echo "Админка будет доступна на http://localhost:8000"
echo "Нажми Ctrl+C для остановки"
echo ""

python launch.py
