@echo off
rem Doble clic: prepara el entorno y prueba el adaptador de crAPI (sin abrir el navegador).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0preparar_y_probar_crapi.ps1"
echo.
echo Listo. La salida quedo en preparar_y_probar_crapi.txt
pause
