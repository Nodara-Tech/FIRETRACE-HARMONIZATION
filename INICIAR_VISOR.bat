@echo off
cd /d "%~dp0"
title Nodara Tech - Observatorio de Incendios
echo Iniciando Nodara Tech...
py aplicacion\visor_incendios.py
if errorlevel 1 (
 echo.
 echo El visor no pudo iniciar. Revisa el mensaje anterior.
 pause
)
