@echo off
cd /d "%~dp0"
py aplicacion\migrar_datos_anteriores.py
if errorlevel 1 (
 echo [ERROR] No se pudieron importar algunos archivos.
)
pause
