@echo off
title Habilitar Autoarranque al Despertar
color 0A

:: Chequear y solicitar permisos de Administrador
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Solicitando permisos de Administrador...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo Creando tarea programada para abrir el bot al despertar la PC...
schtasks /create /tn "PiBot_Wakeup" /xml "C:\Users\Guille\Downloads\Bot-08-09\task.xml" /f

echo.
echo =================================================================
echo EXITO: Tarea creada. El bot se abrira al despertar la PC.
echo =================================================================
echo.
pause
