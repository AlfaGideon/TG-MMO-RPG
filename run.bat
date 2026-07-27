@echo off
if exist venv\Scripts\activate.bat call venv\Scripts\activate.bat
if not exist data mkdir data

echo Starting bot...
start python -m bot.main

echo Starting admin panel on http://localhost:8000 ...
start python -m admin.main

echo Both services started.
pause
