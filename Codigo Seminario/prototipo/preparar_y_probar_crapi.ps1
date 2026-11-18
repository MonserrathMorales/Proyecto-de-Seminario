# Rehace el .venv si no funciona en este equipo, instala requirements.txt y Chromium,
# y corre verificar_adaptadores.py y probar_crapi.py. Todo queda también en preparar_y_probar_crapi.txt.
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
$log = Join-Path $PSScriptRoot "preparar_y_probar_crapi.txt"
"" | Set-Content -Encoding UTF8 $log
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"

function Paso($texto) { "`n===== $texto =====" | Tee-Object -FilePath $log -Append }
function Correr($exe, [string[]]$argumentos) {
    & $exe @argumentos 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $log -Append
    "(código de salida: $LASTEXITCODE)" | Tee-Object -FilePath $log -Append
}

Paso "Python del sistema"
$base = $null
foreach ($cand in @(@("py", "-3.13"), @("py", "-3.12"), @("python"))) {
    $exe = $cand[0]; $resto = @($cand | Select-Object -Skip 1)
    try {
        $v = & $exe @resto -c "import sys; print(sys.version_info >= (3, 12), sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $v -like "True*") { $base = $cand; "Se usa: $v" | Tee-Object -FilePath $log -Append; break }
    } catch {}
}
if (-not $base) { "No se encontró Python 3.12 o 3.13 (py -3.13, py -3.12 ni python)." | Tee-Object -FilePath $log -Append; exit 1 }

Paso "Entorno virtual"
$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$ok = $false
if (Test-Path $venvPy) { & $venvPy --version 2>$null | Out-Null; $ok = ($LASTEXITCODE -eq 0) }
if ($ok) { "El .venv funciona; se reutiliza." | Tee-Object -FilePath $log -Append }
else {
    "El .venv no funciona en este equipo: se rehace con --clear." | Tee-Object -FilePath $log -Append
    $exe = $base[0]; $resto = @($base | Select-Object -Skip 1)
    Correr $exe ($resto + @("-m", "venv", ".venv", "--clear"))
}
Correr $venvPy @("--version")

Paso "Paquetes (requirements.txt)"
Correr $venvPy @("-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", "..\prueba_concepto\requirements.txt")
Paso "Chromium de Playwright"
Correr $venvPy @("-m", "playwright", "install", "chromium")

Paso "Contenedores de crAPI"
Push-Location "..\crAPI-main\deploy\docker"
Correr "docker" @("compose", "ps", "--format", "table {{.Name}}\t{{.Status}}")
Pop-Location

Paso "python verificar_adaptadores.py"
Correr $venvPy @("verificar_adaptadores.py")
Paso "python probar_crapi.py"
Correr $venvPy @("probar_crapi.py")
Paso "FIN"
