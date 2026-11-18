@echo off
rem Campaña con crAPI: 5 repeticiones en modo reglas_llm con gemma4:e4b (necesita crAPI y Ollama; abre Chromium).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0campana_crapi.ps1"
echo.
echo Listo. La salida quedo en campana_crapi.txt y en datos\campana_^<fecha^>
pause
