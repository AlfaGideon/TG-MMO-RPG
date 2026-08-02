@echo off
chcp 65001 >nul
REM Совместимость со старой точкой входа.
REM Весь запуск теперь находится в «Запустить_бота_Windows.bat».
call "%~dp0Запустить_бота_Windows.bat"
