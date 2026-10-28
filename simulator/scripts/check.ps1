[CmdletBinding()]
param(
    [switch]$Runtime,
    [ValidateRange(1,65535)][int]$WebPort = 8000,
    [ValidateRange(1,65535)][int]$MqttPort = 3333,
    [string]$MqttHost = '127.0.0.1',
    [switch]$BrokerOnly
)

. (Join-Path $PSScriptRoot 'common.ps1')
$checksFailed = $false
Push-Location -LiteralPath $script:RepositoryRoot
try {
    if (-not $BrokerOnly) {
        if (-not (Test-Path -LiteralPath $script:VenvPython -PathType Leaf)) {
            Write-Host 'Python environment: missing. Run simulator/scripts/start.ps1 -Install.'
            $checksFailed = $true
        } else {
            & $script:VenvPython -m simulator.server.main --check
            if ($LASTEXITCODE -ne 0) { $checksFailed = $true }
        }
    }
    $ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($ffmpeg) { Write-Host "FFmpeg: $($ffmpeg.Source)" }
    else { Write-Host 'FFmpeg: unavailable; real HEVC/H.264 video cannot be exercised.' }
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if ($docker) {
        & docker compose version
        if ($LASTEXITCODE -ne 0) { Write-Host 'Docker Compose: unavailable.' }
        & docker info --format '{{.ServerVersion}}'
        if ($LASTEXITCODE -ne 0) { Write-Host 'Docker daemon: unavailable.' }
    } else { Write-Host 'Docker: unavailable; no container deployment test can run.' }
    if ($Runtime) {
        if (Test-MqttBroker $MqttHost $MqttPort) { Write-Host "MQTT handshake: passed at ${MqttHost}:$MqttPort" }
        else { Write-Host 'MQTT handshake: failed.'; $checksFailed = $true }
        if (-not $BrokerOnly) {
            $health = Get-SimulatorHealth $WebPort
            if ($null -ne $health -and $health.status -eq 'ok') {
                Write-Host "Simulator HTTP health: passed (instance $($health.instanceId))."
            } else { Write-Host 'Simulator HTTP health: failed.'; $checksFailed = $true }
        }
    }
} finally { Pop-Location }
if ($checksFailed) { exit 1 }
exit 0
