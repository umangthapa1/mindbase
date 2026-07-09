@echo off
REM Mindbase Startup Script for Windows

setlocal enabledelayedexpansion

echo 🚀 Mindbase - AI Workspace
echo ==========================
echo.

REM Check if virtual environment exists
if not exist "venv" (
    echo 📦 Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install/update dependencies
if not exist "venv\Scripts\uvicorn.exe" (
    echo 📥 Installing dependencies...
    pip install -q -r backend\requirements.txt
)

echo.
echo 🎯 Starting Mindbase...
echo    Open browser: http://localhost:8000
echo    Press Ctrl+C to stop
echo.

cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause
