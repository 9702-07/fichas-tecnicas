@echo off
title Fichas Tecnicas - Pacific Control SAC
cd /d "C:\Fichas tecnicas"

REM --- Ruta de Python confirmada, con respaldo al 'python' del PATH ---
set "PY=C:\Users\USER\AppData\Local\Programs\Python\Python314\python.exe"
if not exist "%PY%" set "PY=python"

REM --- Si ya hay un servidor escuchando en el puerto 5000, solo abrir navegador ---
netstat -ano | findstr /c:":5000 " >nul 2>&1
if %errorlevel%==0 (
    echo El servidor ya esta corriendo. Abriendo el navegador...
    goto abrir
)

echo Iniciando el servidor de Fichas Tecnicas...
start "Servidor Fichas Tecnicas" "%PY%" app.py

echo Esperando a que el servidor arranque...
set /a n=0
:esperar
timeout /t 1 /nobreak >nul
netstat -ano | findstr /c:":5000 " >nul 2>&1
if %errorlevel%==0 goto abrir
set /a n+=1
if %n% lss 15 goto esperar

:abrir
start "" "http://127.0.0.1:5000"
exit /b
