@echo off
cd /d "%~dp0"
py aplicacion\pruebas_rapidas.py
if errorlevel 1 (pause & exit /b 1)
py aplicacion\pruebas_v3.py
pause
