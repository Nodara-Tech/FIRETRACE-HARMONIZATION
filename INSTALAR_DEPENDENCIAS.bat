@echo off
cd /d "%~dp0"
py -m pip install -r requirements.txt
if errorlevel 1 (
 echo.
 echo [ERROR] Comprueba que Python y pip esten instalados.
 pause
 exit /b 1
)
echo.
echo Dependencias instaladas correctamente.
pause
