@echo off
title KILLAPP - DETENER BOT DE TRADING
echo =====================================================
echo          DETENIENDO BOT DE TRADING (KILLAPP)
echo =====================================================
echo.
echo Creando bandera de apagado...
echo killapp > killapp.flag

echo Cerrando procesos de Python del bot...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.CommandLine -like '*run_bot.py*' -or $_.CommandLine -like '*main.py*') -and $_.Name -like '*python*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" 2>nul
taskkill /f /fi "WINDOWTITLE eq BOT DE TRADING*" 2>nul

echo.
echo [OK] Bot de trading detenido por completo.
echo.
timeout /t 3 >nul
exit
