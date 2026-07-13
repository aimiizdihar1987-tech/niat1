@echo off
chcp 65001 >nul
title Niat - Buka Akses WiFi (port 8050)
REM ============================================================
REM  KLIK KANAN fail ini -> "Run as administrator"
REM  Ia membenarkan telefon/tablet pada WiFi YANG SAMA membuka
REM  pautan Niat (port 8050). Hanya rangkaian "Private".
REM  Tak mendedahkan server ke internet.
REM ============================================================

netsh advfirewall firewall delete rule name="Niat 8050" >nul 2>&1
netsh advfirewall firewall add rule name="Niat 8050" dir=in action=allow protocol=TCP localport=8050 profile=private

if %errorlevel%==0 (
  echo.
  echo  [OK] Port 8050 sudah dibuka untuk WiFi Private.
  echo       Telefon pada WiFi yang sama kini boleh buka pautan email.
) else (
  echo.
  echo  [GAGAL] Pastikan anda "Run as administrator".
)
echo.
pause
