@echo off
REM Niat background server launcher (windowless via pythonw).
REM Started automatically at login by the "Niat Server" scheduled task.
cd /d "%~dp0"
set PORT=8050
set HOST=0.0.0.0
start "" /b pythonw server.py
