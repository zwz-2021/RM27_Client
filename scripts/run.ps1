#requires -Version 5.1
[CmdletBinding(DefaultParameterSetName = 'Client')]
param(
    [Parameter(Position = 0)]
    [ValidateSet('Debug', 'Release')]
    [string]$Configuration = 'Debug',

    [Parameter(Position = 1, ParameterSetName = 'Client')]
    [ValidateSet('official', 'simulation', 'preview')]
    [string]$Mode = 'official',

    [Parameter(Position = 2, ParameterSetName = 'Client')]
    [string]$ConfigFile,
    [Parameter(Position = 3, ParameterSetName = 'Client')]
    [string]$LogDirectory,

    [Parameter(Mandatory, ParameterSetName = 'Hevc')]
    [string[]]$HevcFile,
    [Parameter(ParameterSetName = 'Hevc')]
    [ValidateRange(1, 2147483647)]
    [int]$StopAfter,
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
    # Resolve relative input paths against the repository, even from another cwd.
    $programArguments = @()
    $program = 'RM27_Client'
    if ($PSCmdlet.ParameterSetName -eq 'Hevc') {
        $program = 'RM27_HevcDecodeProbe'
        if ($PSBoundParameters.ContainsKey('StopAfter')) {
            $programArguments += @('--stop-after', [string]$StopAfter)
        }
        foreach ($file in $HevcFile) {
            if ([IO.Path]::IsPathRooted($file)) {
                $programArguments += $file
            }
            else {
                $programArguments += (Join-Path $projectRoot $file)
            }
        }
    }
    elseif ($ConfigFile) {
        if (-not [IO.Path]::IsPathRooted($ConfigFile)) {
            $ConfigFile = Join-Path $projectRoot $ConfigFile
        }
        if (-not (Test-Path -LiteralPath $ConfigFile -PathType Leaf)) {
            throw "Configuration file not found: $ConfigFile"
        }
        $programArguments += @('--config', $ConfigFile)
    }
    elseif ($Mode -eq 'simulation') {
        $programArguments += @('--config', (Join-Path $projectRoot 'configs/simulation.example.json'))
    }
    elseif ($Mode -eq 'preview') {
        $programArguments += @('--config', (Join-Path $projectRoot 'configs/preview.example.json'))
    }
    if ($LogDirectory) {
        if (-not [IO.Path]::IsPathRooted($LogDirectory)) {
            $LogDirectory = Join-Path $projectRoot $LogDirectory
        }
        $programArguments += @('--log-dir', $LogDirectory)
    }

    if (-not $SkipBuild) {
        & (Join-Path $PSScriptRoot 'build.ps1') -Configuration $Configuration -HevcProbe:($PSCmdlet.ParameterSetName -eq 'Hevc')
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }

    $executable = Join-Path $buildDirectory "bin/$program.exe"
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
    $previousEncoding = [Console]::OutputEncoding
    Push-Location -LiteralPath $projectRoot
    try {
        $env:PATH = "$qtBin;$compilerBin;$previousPath"
        Write-Host "Running $executable"
        if ($PSCmdlet.ParameterSetName -eq 'Hevc') {
            [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
            & $executable @programArguments
        }
        else {
            # Wait for the GUI executable on Windows.
            & $executable @programArguments | Out-Host
        }
        $programExitCode = $LASTEXITCODE
    }
    finally {
        if ($PSCmdlet.ParameterSetName -eq 'Hevc') {
            [Console]::OutputEncoding = $previousEncoding
        }
        $env:PATH = $previousPath
        Pop-Location
    }
    if ($programExitCode -ne 0) {
        throw "$program exited with code $programExitCode."
    }
}
catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
exit 0
