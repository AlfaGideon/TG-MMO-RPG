@echo off
chcp 65001 >nul
title Shadow Lands — запуск сервера
echo.
echo  ==========================================
echo   🌑 Shadow Lands — запуск сервера
echo  ==========================================
echo   ОБНОВЛЕНИЯ ТЫКАТЬ НЕ НАДО — обновления
echo   делаются КНОПКОЙ в самой админ-панели:
echo   Настройки  →  Обновить с GitHub
echo  ==========================================
echo.

:: Проверка Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден!
    echo Скачай и установи: https://python.org/downloads
    echo ☑️ Обязательно поставь галочку "Add Python to PATH"
    pause
    exit /b
)

:: Проверка Git
git --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Git не найден!
    echo Скачай и установи: https://git-scm.com/download/win
    pause
    exit /b
)

:: Если мы не в папке проекта — скачиваем его (только первый раз)
if not exist "launch.py" (
    echo 📥 Первый запуск — скачиваю проект с GitHub...
    cd /d %~dp0
    git clone https://github.com/AlfaGideon/TG-MMO-RPG.git
    cd TG-MMO-RPG
)

echo 🐍 Создаю виртуальное окружение (если его нет)...
if not exist "venv" python -m venv venv

echo ⚡ Активирую окружение...
call venv\Scripts\activate.bat

echo 📦 Устанавливаю библиотеки...
pip install -q -r requirements.txt

echo.
echo  ==========================================
echo   ✅ Сервер запускается!
echo  ==========================================
echo.
echo   🌐 Открой админку в браузере: http://localhost:8000
echo   🕹 Затем в админке: Настройки → Запустить бота
echo   🔄 Обновления: Настройки → Обновить с GitHub
echo.
echo   👉 Держи это окно ОТКРЫТЫМ, пока хочешь,
echo      чтобы бот и админка работали.
echo      Чтобы остановить — нажми Ctrl+C
echo.

python launch.py

pause
