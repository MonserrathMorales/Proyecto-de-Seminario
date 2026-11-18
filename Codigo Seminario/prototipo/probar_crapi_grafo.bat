@echo off
rem Doble clic: flujo completo con crAPI (abre Chromium; no lo cierres mientras corre).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0probar_crapi_grafo.ps1"
echo.
echo Listo. La salida quedo en probar_crapi_grafo.txt
pause
