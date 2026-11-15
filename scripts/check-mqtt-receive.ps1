#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('Debug', 'Release')]
    [string]$Configuration = 'Debug',
    [switch]$SkipBuild,
    [ValidateRange(1, 1000)][int]$Cycles = 100
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$buildDirectory = Join-Path $projectRoot ('build/local-' + $Configuration.ToLowerInvariant())
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
        throw 'Install simulator dependencies first: simulator/scripts/start.ps1 -Install'
    }
    & $python -c 'import amqtt, requests, socketio, websocket'
    if ($LASTEXITCODE -ne 0) {
        throw 'Install test dependencies: simulator/.venv/Scripts/python.exe -m pip install -e "simulator[test]"'
    }
    $oldPath = $env:PATH
    try {
        $env:PATH = (Join-Path $qtRoot 'bin') + ";$compilerBin;$oldPath"
        & $ctest --test-dir $buildDirectory --output-on-failure -R '^basic_session$'
        if ($LASTEXITCODE -ne 0) { throw 'Client state/session checks failed.' }
        Push-Location -LiteralPath $projectRoot
        try {
            & $python (Join-Path $projectRoot 'tests/check_mqtt_receive.py') --client-check (Join-Path $buildDirectory 'bin/RM27_MqttCheck.exe') --cycles $Cycles
            if ($LASTEXITCODE -ne 0) { throw 'Real Qt MQTT receive checks failed; see printed evidence directory.' }
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
