@echo off
cd /d "%~dp0"

if exist venv\Scripts\activate.bat call venv\Scripts\activate.bat
if not exist data mkdir data

echo 🌑 Shadow Lands — запуск единого сервера
echo Админка будет доступна на http://localhost:8000
echo Закрой это окно для остановки
echo.

python launch.py
pause
