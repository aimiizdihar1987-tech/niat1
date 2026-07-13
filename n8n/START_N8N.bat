@echo off
REM Starts n8n (visual workflow app) for Niat.
REM Open http://localhost:5678 in your browser after it says "Editor is now accessible".
set GENERIC_TIMEZONE=Asia/Kuala_Lumpur
set TZ=Asia/Kuala_Lumpur
REM Allow workflows to read Niat's timetable.json and reminder_config.txt
set N8N_RESTRICT_FILE_ACCESS_TO=C:\Users\HP\Desktop\PRESTIJ KAK AIMI;C:\Users\HP\.n8n-files
call "%APPDATA%\npm\n8n.cmd"
