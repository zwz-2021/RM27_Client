#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('Debug', 'Release')]
    [string]$Configuration = 'Debug',
    [switch]$SkipBuild
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$presetName = 'local-' + $Configuration.ToLowerInvariant()
$buildDirectory = Join-Path $projectRoot "build/$presetName"
try {
    if (-not $SkipBuild) {
        & (Join-Path $PSScriptRoot 'build.ps1') -Configuration $Configuration
        if ($LASTEXITCODE -ne 0) { throw 'Client build failed.' }
    }
    $cache = Get-Content -LiteralPath (Join-Path $buildDirectory 'CMakeCache.txt') -Encoding UTF8
    $qtLine = $cache | Where-Object { $_ -match '^Qt6_DIR:[^=]+=' } | Select-Object -First 1
    $compilerLine = $cache | Where-Object { $_ -match '^CMAKE_CXX_COMPILER:[^=]+=' } | Select-Object -First 1
    $ctestLine = $cache | Where-Object { $_ -match '^CMAKE_CTEST_COMMAND:[^=]+=' } | Select-Object -First 1
    if (-not $qtLine -or -not $compilerLine -or -not $ctestLine) { throw 'Build cache is incomplete.' }
    $qtRoot = [IO.Path]::GetFullPath((Join-Path ($qtLine -replace '^[^=]+=', '') '../../..'))
    $compilerBin = Split-Path -Parent ($compilerLine -replace '^[^=]+=', '')
    $ctest = $ctestLine -replace '^[^=]+=', ''
    $python = Join-Path $projectRoot 'simulator/.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        throw 'Install simulator Python dependencies first: simulator/scripts/start.ps1 -Install'
    }
    $oldPath = $env:PATH
    try {
        $env:PATH = (Join-Path $qtRoot 'bin') + ";$compilerBin;$oldPath"
        & $ctest --test-dir $buildDirectory --output-on-failure -R '^protocol_basic$'
        if ($LASTEXITCODE -ne 0) { throw 'C++ basic protocol checks failed.' }
        & $python (Join-Path $projectRoot 'tests/check_basic_data.py') --client-check (Join-Path $buildDirectory 'bin/RM27_ProtocolCheck.exe')
        if ($LASTEXITCODE -ne 0) { throw 'Python/C++ basic protocol checks failed.' }
        Push-Location -LiteralPath $projectRoot
        try {
            & $python -m simulator.tools.check_base_data
            if ($LASTEXITCODE -ne 0) { throw 'Simulator basic payload and console checks failed.' }
        }
        finally { Pop-Location }
    }
    finally { $env:PATH = $oldPath }
}
catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
exit 0
