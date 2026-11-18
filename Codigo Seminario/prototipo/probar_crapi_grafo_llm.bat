@echo off
rem Doble clic: flujo completo con crAPI en modo reglas_llm (necesita Ollama abierto; abre Chromium).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0probar_crapi_grafo_llm.ps1"
echo.
echo Listo. La salida quedo en probar_crapi_grafo_llm.txt
pause
