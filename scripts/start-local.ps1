$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root ".venv"
$python = Get-Command py -ErrorAction SilentlyContinue

if (-not $python) {
    $python = Get-Command python -ErrorAction SilentlyContinue
}

if (-not $python) {
    Write-Error "Python 3.11 atau lebih baru belum terpasang. Unduh dari https://www.python.org/downloads/"
}

if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
    & $python.Source -m venv $venv
}

$venvPython = Join-Path $venv "Scripts\python.exe"
& $venvPython -m pip install --disable-pip-version-check -r (Join-Path $root "requirements.txt")

Start-Process "http://127.0.0.1:5177"
& $venvPython (Join-Path $root "app.py")

