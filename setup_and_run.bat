@echo off
chcp 65001 >nul
title Shadow Lands — Запуск
echo.
echo  ==========================================
echo   🌑 Shadow Lands — Автозапуск
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

:: Если мы уже в папке проекта — пропускаем клонирование
if exist "launch.py" (
    echo 📁 Проект уже скачан
    goto :RUN
)

:: Скачивание
echo 📥 Скачиваю проект с GitHub...
cd %USERPROFILE%\Desktop
git clone https://github.com/AlfaGideon/TG-MMO-RPG.git
cd TG-MMO-RPG

:RUN
echo 🐍 Создаю виртуальное окружение...
if not exist "venv" python -m venv venv

echo ⚡ Активирую окружение...
call venv\Scripts\activate.bat

echo 📦 Устанавливаю библиотеки...
pip install -q -r requirements.txt

echo.
echo  ==========================================
echo   ✅ Готово! Запускаю сервер...
echo  ==========================================
echo.
echo   🌐 Админка: http://localhost:8000
echo.
echo   Открой эту ссылку в браузере,
echo   перейди в Настройки, вставь токен бота,
echo   нажми Запустить бота.
echo.
echo   Для остановки нажми Ctrl+C
echo.

python launch.py
