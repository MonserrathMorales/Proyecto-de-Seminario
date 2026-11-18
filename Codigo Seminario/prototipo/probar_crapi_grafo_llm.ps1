# Corre probar_crapi.py --grafo --modo reglas_llm con el .venv (abre Chromium y usa mitmproxy en el puerto 8080).
# La salida queda también en probar_crapi_grafo_llm.txt.
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$log = Join-Path $PSScriptRoot "probar_crapi_grafo_llm.txt"
"" | Set-Content -Encoding UTF8 $log
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
$env:PATH = (Join-Path $PSScriptRoot ".venv\Scripts") + ";" + $env:PATH   # para que el Explorador encuentre mitmdump
$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

function Paso($texto) { "`n===== $texto =====" | Out-File -Append -Encoding UTF8 $log; Write-Host "`n===== $texto =====" }
function Correr($exe, [string[]]$argumentos) {
    & $exe @argumentos 2>&1 | ForEach-Object { $l = "$_"; Write-Host $l; $l | Out-File -Append -Encoding UTF8 $log }
    "(código de salida: $LASTEXITCODE)" | Out-File -Append -Encoding UTF8 $log
}

Paso "Comprobaciones previas"
Correr $venvPy @("-c", "import shutil; print('mitmdump:', shutil.which('mitmdump'))")
$ocupado = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
if ($ocupado) { "AVISO: el puerto 8080 está ocupado por el proceso $($ocupado.OwningProcess); cierra ese programa." | Tee-Object -Variable m | Out-File -Append -Encoding UTF8 $log; Write-Host $m }
Paso "Ollama"
try {
    $tags = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 5
    $modelos = @($tags.models | ForEach-Object { $_.name })
    $m = "Ollama responde. Modelos: " + ($modelos -join ", "); Write-Host $m; $m | Out-File -Append -Encoding UTF8 $log
    if ($modelos -notcontains "gemma4:e4b") {
        $m = "AVISO: falta gemma4:e4b (ollama pull gemma4:e4b). Solo se usará si quedan candidatos pendientes."
        Write-Host $m; $m | Out-File -Append -Encoding UTF8 $log
    }
} catch {
    $m = "AVISO: Ollama no responde en localhost:11434. Ábrelo antes; si quedan candidatos pendientes, el Analista fallará."
    Write-Host $m; $m | Out-File -Append -Encoding UTF8 $log
}
Paso "python probar_crapi.py --grafo --modo reglas_llm"
Correr $venvPy @("probar_crapi.py", "--grafo", "--modo", "reglas_llm")
Paso "FIN"
