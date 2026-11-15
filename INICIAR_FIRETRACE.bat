@echo off
cd /d "%~dp0"
py aplicacion\visor_incendios.py
if errorlevel 1 pause
