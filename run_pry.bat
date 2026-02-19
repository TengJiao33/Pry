@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat

if "%1"=="--debug" (
    echo Starting Pry in DEBUG mode...
    python src\window_monitor.py --debug
    pause
) else (
    echo Starting Pry in Silent mode...
    start "" ".venv\Scripts\pythonw.exe" "src\window_monitor.py"
)
