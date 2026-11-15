@echo off
cd /d "%~dp0"
py -m pip install -r requirements.txt
if errorlevel 1 (echo ERROR al instalar dependencias & pause & exit /b 1)
py aplicacion\pruebas_problema4.py
if errorlevel 1 (echo ERROR pruebas sinteticas & pause & exit /b 1)
py aplicacion\pruebas_problema4_reales.py
if errorlevel 1 (echo ERROR pruebas H3 reales & pause & exit /b 1)
echo P4: pruebas ejecutadas. Verifica la interfaz en el navegador.
pause
