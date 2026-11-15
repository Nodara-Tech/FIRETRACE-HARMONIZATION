@echo off
cd /d "%~dp0"
echo ==== NODARA P3: PRUEBAS UNITARIAS SINTETICAS ====
py aplicacion\pruebas_problema3.py
if errorlevel 1 goto :error
echo.
echo ==== NODARA P3: H3 REAL + NASA FIRMS ====
py aplicacion\pruebas_problema3_reales.py
if errorlevel 1 goto :error
echo.
echo TODAS LAS PRUEBAS P3 PASARON (integridad, NO exactitud cientifica).
pause
exit /b 0
:error
echo.
echo ERROR: revisa mensaje anterior; verifica py -m pip install -r requirements.txt
pause
exit /b 1
