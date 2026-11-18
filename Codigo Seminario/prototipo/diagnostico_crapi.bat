@echo off
rem Diagnostico para la prueba con crAPI: no instala ni cambia nada.
cd /d "%~dp0"
echo === Usuario y fecha > diagnostico_crapi.txt
whoami >> diagnostico_crapi.txt 2>&1
echo %DATE% %TIME% >> diagnostico_crapi.txt 2>&1
echo === Python del .venv >> diagnostico_crapi.txt 2>&1
.venv\Scripts\python.exe --version >> diagnostico_crapi.txt 2>&1
.venv\Scripts\python.exe -c "import requests, pydantic, langgraph; print('base ok')" >> diagnostico_crapi.txt 2>&1
.venv\Scripts\python.exe -c "import mitmproxy; print('mitmproxy ok')" >> diagnostico_crapi.txt 2>&1
.venv\Scripts\python.exe -c "import playwright; print('playwright ok')" >> diagnostico_crapi.txt 2>&1
echo === Python del sistema >> diagnostico_crapi.txt 2>&1
where python >> diagnostico_crapi.txt 2>&1
where py >> diagnostico_crapi.txt 2>&1
py -0p >> diagnostico_crapi.txt 2>&1
echo === Docker >> diagnostico_crapi.txt 2>&1
docker --version >> diagnostico_crapi.txt 2>&1
docker compose version >> diagnostico_crapi.txt 2>&1
docker info --format "{{.ServerVersion}} mem={{.MemTotal}} cpu={{.NCPU}}" >> diagnostico_crapi.txt 2>&1
docker ps --format "{{.Names}} {{.Status}} {{.Ports}}" >> diagnostico_crapi.txt 2>&1
echo === RAM >> diagnostico_crapi.txt 2>&1
powershell -NoProfile -Command "$o=Get-CimInstance Win32_OperatingSystem; 'Total ' + [math]::Round($o.TotalVisibleMemorySize/1MB,1) + ' GB, libre ' + [math]::Round($o.FreePhysicalMemory/1MB,1) + ' GB'" >> diagnostico_crapi.txt 2>&1
echo === Puertos >> diagnostico_crapi.txt 2>&1
netstat -ano | findstr /R ":8888 :8025 :8080 :3000" >> diagnostico_crapi.txt 2>&1
echo === FIN >> diagnostico_crapi.txt 2>&1
