@echo off
title BOT DE TRADING POCKET OPTION - AUTOSTART
cd /d "%~dp0"

echo =================================================================
echo        BOT DE TRADING - ARRANQUE AUTOMATICO DE WINDOWS
echo =================================================================
echo [INFO] Directorio de trabajo: %CD%
echo [INFO] Fecha y hora de inicio: %DATE% %TIME%
echo.
echo [1/2] Esperando 10 segundos a que Windows inicialice la conexion de red...
timeout /t 10 /nobreak >nul

echo [2/2] Lanzando Bot de Trading con Supervisor...
echo.
"C:\Users\Guille\AppData\Local\Programs\Python\Python314\python.exe" run_bot.py config.json

echo.
echo =================================================================
echo   SESION COMPLETADA O BOT DETENIDO POR KILLAPP
echo =================================================================
echo Cerrando ventana en 5 segundos...
timeout /t 5 >nul
exit
