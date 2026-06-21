@echo off
REM Launch the bot using its own virtual environment.
cd /d "%~dp0"
"venv\Scripts\python.exe" bot.py
echo.
echo Bot stopped. Press any key to close.
pause >nul
