@echo off
chcp 65001 >nul
title Niat - AI-Powered Classroom
cd /d "%~dp0"

REM Use port 8050 (port 8000 is used by the TinyLlama app)
set PORT=8050
set HOST=0.0.0.0

echo ============================================================
echo   Niat - AI-Powered Classroom (English, KSSM Form 3)
echo ============================================================
echo.
echo   Starting the server... (DO NOT close this window)
echo   Your browser will open automatically in a moment.
echo.
echo   To stop: close this window or press Ctrl+C.
echo.
echo   Backups: question bank + saved lessons are backed up
echo   daily at 5pm to Documents\Niat Backups.
echo.
echo   All commands: see COMMANDS.md in this folder.
echo ============================================================
echo.

REM Open the browser after 2 seconds (give the server time to start)
start "" /b cmd /c "timeout /t 2 >nul & start "" http://localhost:8050"

REM Run the server (stays running in this window)
python server.py

echo.
echo The server has stopped. Press any key to close.
pause >nul
