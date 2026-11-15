@echo off
cd /d "%~dp0"
echo Comprobacion LOCAL del motor H3 y cuadricula v2.
echo No necesita que el servidor web este ejecutandose.
py aplicacion\pruebas_v3.py
if errorlevel 1 (
  echo [ERROR] Revisa el mensaje. Si falta H3, ejecuta INSTALAR_DEPENDENCIAS.bat.
  pause
  exit /b 1
)
echo.
echo Para revisar tambien el servidor en funcionamiento: py aplicacion\diagnosticar_visor.py
pause
