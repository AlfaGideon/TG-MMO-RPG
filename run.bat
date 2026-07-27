@echo off
chcp 65001 >nul
echo 🌑 Shadow Lands — запуск...

if not exist venv (
    echo Создаю виртуальное окружение...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo Устанавливаю зависимости...
pip install -q -r requirements.txt

echo Запускаю сервер...
start /B python -m uvicorn admin.main:app --host 0.0.0.0 --port 8000 --lifespan on > srv.log 2>&1

timeout /t 5 /nobreak >nul

echo.
echo ==========================================
echo ✅ Сервер запущен!
echo.
echo Открой в браузере: http://localhost:8000
echo.
echo Если нужна публичная ссылка:
echo 1. Установи Node.js
echo 2. В новом окне выполни: npx localtunnel --port 8000
echo ==========================================
echo.
echo Нажми Ctrl+C для остановки
echo.
python launch.py
