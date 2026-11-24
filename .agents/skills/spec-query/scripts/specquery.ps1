<#
.SYNOPSIS
    Runs specquery.py in this skill's own venv, forwarding every argument.
.DESCRIPTION
    Creates the venv beside this script on first use and reinstalls requirements.txt whenever
    that file changes. Run `specquery.ps1 -h` for the commands specquery.py accepts.
#>
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$SpecQueryArgs
)

$ErrorActionPreference = 'Stop'

$venvDir = Join-Path $PSScriptRoot '.venv'
$python = Join-Path $venvDir 'Scripts\python.exe'
$requirements = Join-Path $PSScriptRoot 'requirements.txt'
$installedStamp = Join-Path $venvDir 'requirements.sha256'

if (-not (Test-Path $python)) {
    Write-Host "[BOOTSTRAP] Creating venv at $venvDir"
    python -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { Write-Error 'Failed to create venv' }
}

$requirementsHash = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash
if (-not (Test-Path $installedStamp) -or (Get-Content -LiteralPath $installedStamp -Raw) -ne $requirementsHash) {
    Write-Host '[BOOTSTRAP] Installing Python dependencies...'
    & $python -m pip install --quiet --disable-pip-version-check -r $requirements
    if ($LASTEXITCODE -ne 0) { Write-Error 'Failed to install dependencies' }
    Set-Content -LiteralPath $installedStamp -Value $requirementsHash -NoNewline
}

& $python (Join-Path $PSScriptRoot 'specquery.py') @SpecQueryArgs
exit $LASTEXITCODE
