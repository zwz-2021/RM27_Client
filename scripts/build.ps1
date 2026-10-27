#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('Debug', 'Release')]
    [string]$Configuration = 'Debug',

    [ValidateRange(1, 256)]
    [int]$Jobs = [Math]::Min(8, [Environment]::ProcessorCount)
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$presetName = 'local-' + $Configuration.ToLowerInvariant()

try {
    $userPresetsPath = Join-Path $projectRoot 'CMakeUserPresets.json'
    if (-not (Test-Path -LiteralPath $userPresetsPath -PathType Leaf)) {
        throw 'Copy CMakeUserPresets.json.example to CMakeUserPresets.json and edit its tool paths first.'
    }
    $userPresets = Get-Content -LiteralPath $userPresetsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $preset = @($userPresets.configurePresets | Where-Object { $_.name -eq $presetName })
    if ($preset.Count -ne 1) {
        throw "Expected exactly one '$presetName' configure preset in CMakeUserPresets.json."
    }

    # Local presets store literal tool paths; CMake resolves the shared inheritance.
    $toolFiles = @{
        RM27_CMAKE_ROOT = 'bin/cmake.exe'
        RM27_QT_ROOT = 'bin/Qt6Core.dll'
        RM27_MINGW_ROOT = 'bin/g++.exe'
        RM27_NINJA_ROOT = 'ninja.exe'
    }
    foreach ($entry in $toolFiles.GetEnumerator()) {
        $root = [string]$preset[0].environment.($entry.Key)
        if ([string]::IsNullOrWhiteSpace($root) -or -not [IO.Path]::IsPathRooted($root)) {
            throw "Set $($entry.Key) to an absolute installation path in preset '$presetName'."
        }
        $toolPath = Join-Path $root $entry.Value
        if (-not (Test-Path -LiteralPath $toolPath -PathType Leaf)) {
            throw "Cannot find '$toolPath'. Update $($entry.Key) in CMakeUserPresets.json."
        }
    }
    $cmake = Join-Path $preset[0].environment.RM27_CMAKE_ROOT 'bin/cmake.exe'
    $executable = [IO.Path]::GetFullPath((Join-Path $projectRoot "build/$presetName/bin/RM27_Client.exe"))
    $runningClient = Get-Process -Name RM27_Client -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq $executable }
    if ($runningClient) {
        throw "Close the running $presetName client before building; Windows locks its executable."
    }

    Push-Location -LiteralPath $projectRoot
    try {
        Write-Host "Configuring $presetName ..."
        & $cmake --preset $presetName
        if ($LASTEXITCODE -ne 0) {
            throw "CMake configure failed (exit $LASTEXITCODE)."
        }
        Write-Host "Building $presetName ..."
        & $cmake --build --preset $presetName --parallel $Jobs
        if ($LASTEXITCODE -ne 0) {
            throw "CMake build failed (exit $LASTEXITCODE)."
        }
        Write-Host "Built: $executable"
    }
    finally {
        Pop-Location
    }
}
catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
exit 0
