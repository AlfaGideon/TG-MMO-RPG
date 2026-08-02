@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Shadow Lands — сервер и бот

echo.
echo  ==========================================
echo   🌑 Shadow Lands — запуск сервера и бота
echo  ==========================================
echo.
echo   Один проект — одно окно запуска.
echo   Не запускай одновременно run.bat, setup_and_run.bat
echo  или вторую копию этого файла.
echo.

:: Проверка Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден!
    echo Скачай и установи: https://python.org/downloads
    echo ☑️ При установке отметь "Add Python to PATH"
    pause
    exit /b 1
)

:: Если файл запущен рядом с проектом, а не из него — клонируем проект.
if not exist "launch.py" (
    echo 📥 Первый запуск — скачиваю проект с GitHub...
    git --version >nul 2>&1
    if errorlevel 1 (
        echo ❌ Git не найден!
        echo Скачай и установи: https://git-scm.com/download/win
        pause
        exit /b 1
    )
    git clone https://github.com/AlfaGideon/TG-MMO-RPG.git
    if errorlevel 1 (
        echo ❌ Не удалось скачать проект.
        pause
        exit /b 1
    )
    cd /d "%CD%\TG-MMO-RPG"
)

:: Не создаём второй сервер: это предотвращает конфликт бота и порта 8000.
python -c "import socket; s=socket.socket(); s.settimeout(1); busy=s.connect_ex(('127.0.0.1', 8000)) == 0; s.close(); raise SystemExit(0 if busy else 1)"
if not errorlevel 1 goto :ALREADY_RUNNING

echo 🐍 Создаю виртуальное окружение (если его нет)...
if not exist "venv\Scripts\python.exe" python -m venv venv
if errorlevel 1 (
    echo ❌ Не удалось создать виртуальное окружение.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo 📦 Устанавливаю/проверяю библиотеки...
python -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo ❌ Не удалось установить зависимости.
    pause
    exit /b 1
)

echo.
echo  ==========================================
echo   ✅ Запускаю единственный экземпляр сервера
echo  ==========================================
echo.
echo   🏠 Локальная панель: http://localhost:8000
echo   🌐 Публичный HTTPS-адрес Cloudflare появится в этом окне
echo      после запуска и сохранится в Настройках панели.
echo   🕹 Бот запускается в панели: Настройки → Запустить бота
echo   🔄 Обновления: Настройки → Обновить с GitHub
echo.
echo   👉 Не закрывай это окно. Остановка: Ctrl+C
echo.

:: launch.py запускает и панель, и бота (если токен сохранён),
:: и штатный Cloudflare Quick Tunnel. Никакие другие .bat запускать не нужно.
python launch.py

echo.
echo Сервер остановлен.
pause
exit /b

:ALREADY_RUNNING
echo.
echo  ==========================================
echo   ⚠️ Сервер уже запущен на порту 8000.
echo  ==========================================
echo.
echo   Второй экземпляр не запущен: это защищает от
echo   конфликта Telegram-бота (TelegramConflictError).
echo   Открываю уже работающую панель: http://localhost:8000
echo.
start "" "http://localhost:8000"
pause
exit /b 0
