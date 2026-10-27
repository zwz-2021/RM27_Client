#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('Debug', 'Release')]
    [string]$Configuration = 'Debug',

    [ValidateSet('official', 'simulation')]
    [string]$Mode = 'official',

    [string]$ConfigFile,
    [string]$LogDirectory,
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$presetName = 'local-' + $Configuration.ToLowerInvariant()
$buildDirectory = Join-Path $projectRoot "build/$presetName"

function Get-CacheValue([string[]]$Lines, [string]$Name) {
    $pattern = '^' + [regex]::Escape($Name) + ':[^=]+=(.*)$'
    foreach ($line in $Lines) {
        if ($line -match $pattern) {
            return $Matches[1]
        }
    }
    throw "Missing $Name in CMakeCache.txt. Build this configuration first."
}

try {
    # Resolve relative config/log paths against the repository, even from another cwd.
    $clientArguments = @()
    if ($ConfigFile) {
        if (-not [IO.Path]::IsPathRooted($ConfigFile)) {
            $ConfigFile = Join-Path $projectRoot $ConfigFile
        }
        if (-not (Test-Path -LiteralPath $ConfigFile -PathType Leaf)) {
            throw "Configuration file not found: $ConfigFile"
        }
        $clientArguments += @('--config', $ConfigFile)
    }
    elseif ($Mode -eq 'simulation') {
        $clientArguments += @('--config', (Join-Path $projectRoot 'configs/simulation.example.json'))
    }
    if ($LogDirectory) {
        if (-not [IO.Path]::IsPathRooted($LogDirectory)) {
            $LogDirectory = Join-Path $projectRoot $LogDirectory
        }
        $clientArguments += @('--log-dir', $LogDirectory)
    }

    if (-not $SkipBuild) {
        & (Join-Path $PSScriptRoot 'build.ps1') -Configuration $Configuration
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }

    $executable = Join-Path $buildDirectory 'bin/RM27_Client.exe'
    $cachePath = Join-Path $buildDirectory 'CMakeCache.txt'
    if (-not (Test-Path -LiteralPath $executable -PathType Leaf) -or
        -not (Test-Path -LiteralPath $cachePath -PathType Leaf)) {
        throw "No $presetName build found. Run scripts/build.ps1 -Configuration $Configuration first."
    }

    # Use the exact Qt/compiler recorded by CMake, not an unrelated system PATH kit.
    $cache = Get-Content -LiteralPath $cachePath -Encoding UTF8
    $qtPackageDirectory = Get-CacheValue $cache 'Qt6_DIR'
    $qtRoot = [IO.Path]::GetFullPath((Join-Path $qtPackageDirectory '../../..'))
    $qtBin = Join-Path $qtRoot 'bin'
    $compilerBin = Split-Path -Parent (Get-CacheValue $cache 'CMAKE_CXX_COMPILER')
    if (-not (Test-Path -LiteralPath (Join-Path $qtBin 'Qt6Core.dll') -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $compilerBin 'g++.exe') -PathType Leaf)) {
        throw 'The cached Qt/MinGW installation no longer exists. Update local presets and rebuild.'
    }

    $previousPath = $env:PATH
    Push-Location -LiteralPath $projectRoot
    try {
        $env:PATH = "$qtBin;$compilerBin;$previousPath"
        Write-Host "Running $executable"
        # Piping a GUI executable makes PowerShell wait until the client exits.
        & $executable @clientArguments | Out-Host
        $clientExitCode = $LASTEXITCODE
    }
    finally {
        $env:PATH = $previousPath
        Pop-Location
    }
    if ($clientExitCode -ne 0) {
        throw "RM27_Client exited with code $clientExitCode."
    }
}
catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
exit 0
