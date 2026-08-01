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

echo.
echo ==========================================
echo ✅ Сервер запускается!
echo.
echo 🌐 Открой админку в браузере: http://localhost:8000
echo 🕹 Бот запускается в админке: Настройки → Запустить бота
echo    (или сам, если токен уже сохранён в настройках).
echo 📄 launch.py запускается этим скриптом — отдельно его
echo    запускать НЕ нужно.
echo 👉 Держи это окно ОТКРЫТЫМ — Ctrl+C для остановки
echo.
echo ⚠️ Если запущено ещё одно окно/терминал с сервером —
echo    закрой его, иначе бот будет конфликтовать сам с собой.
echo ==========================================
echo.

python launch.py

echo.
echo Сервер остановлен.
pause
