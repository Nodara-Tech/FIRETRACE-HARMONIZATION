@echo off
cd /d "%~dp0"
py -m pip install -r requirements.txt
if errorlevel 1 goto :error
py aplicacion\pruebas_problema5.py
if errorlevel 1 goto :error
py aplicacion\pruebas_problema5_reales.py
if errorlevel 1 goto :error
echo PRUEBAS V3.6 COMPLETADAS
pause
exit /b 0
:error
echo ERROR: revisa los mensajes anteriores y el archivo INSTRUCCIONES_PARCHE_V3_6.txt
pause
exit /b 1
