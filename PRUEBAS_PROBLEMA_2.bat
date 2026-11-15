@echo off
cd /d "%~dp0"
py aplicacion\pruebas_problema1.py
if errorlevel 1 goto error
py aplicacion\pruebas_problema2.py
if errorlevel 1 goto error
echo TODAS LAS PRUEBAS P1 Y P2 PASARON.
pause
exit /b 0
:error
echo ERROR: revisa mensajes anteriores.
pause
exit /b 1
