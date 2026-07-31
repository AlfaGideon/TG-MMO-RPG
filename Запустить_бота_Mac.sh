#!/bin/bash
# Shadow Lands — запуск бота и админки 24/7 (Mac / Linux)
echo ""
echo "=========================================="
echo "  🌑 Shadow Lands — запуск бота и админки"
echo "=========================================="
echo ""

cd "$(dirname "$0")" || exit 1

# Проверка Python
if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ Python не найден!"
    echo "Скачай и установи: https://python.org/downloads"
    exit 1
fi

# Проверка Git
if ! command -v git >/dev/null 2>&1; then
    echo "❌ Git не найден!"
    echo "Скачай и установи: https://git-scm.com/download/mac"
    exit 1
fi

# Если мы не в папке проекта — скачиваем его
if [ ! -f "launch.py" ]; then
    echo "📥 Скачиваю проект с GitHub..."
    git clone https://github.com/AlfaGideon/TG-MMO-RPG.git
    cd TG-MMO-RPG || exit 1
fi

echo "📡 Проверяю обновления с GitHub..."
if git pull; then
    echo "✅ Обновления проверены."
else
    echo "⚠️  Не удалось получить обновления (нет интернета?)"
    echo "   Продолжаю со старой версией."
fi
echo ""

echo "🐍 Создаю виртуальное окружение (если его нет)..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

echo "⚡ Активирую окружение..."
source venv/bin/activate

echo "📦 Устанавливаю библиотеки..."
pip install -q -r requirements.txt

echo ""
echo "=========================================="
echo "  ✅ Всё готово! Запускаю бота и админку..."
echo "=========================================="
echo ""
echo "  🌐 Админка откроется на: http://localhost:8000"
echo ""
echo "  👉 Держи это окно ОТКРЫТЫМ, пока хочешь,"
echo "     чтобы бот и админка работали."
echo ""
echo "  Чтобы остановить — нажми Ctrl+C"
echo ""

python launch.py
