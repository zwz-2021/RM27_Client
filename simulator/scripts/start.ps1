[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$BrokerOnly,
    [switch]$EnableUdpSender,
    [switch]$EnableReceiver,
    [string]$VideoFile,
    [switch]$VideoOnly,
    [ValidateRange(1,65535)][int]$WebPort = 8000,
    [ValidateRange(1,65535)][int]$MqttPort = 3333,
    [string]$MqttHost = '127.0.0.1',
    [string]$TargetIP = '127.0.0.1',
    [ValidateSet(1,2,3,4,5,6,7,101,102,103,104,105,106,107)][int]$CurrentRobotId = 1,
    [string]$Python = 'python'
)

. (Join-Path $PSScriptRoot 'common.ps1')

Push-Location -LiteralPath $script:RepositoryRoot
try {
    if ($Install) {
        if (-not (Test-Path -LiteralPath $script:VenvPython -PathType Leaf)) {
            & $Python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'
            if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or newer is required. Supply -Python with its executable path.' }
            & $Python -m venv (Join-Path $script:SimulatorRoot '.venv')
            if ($LASTEXITCODE -ne 0) { throw 'Creating the simulator virtual environment failed.' }
        }
        & $script:VenvPython -m pip install -e $script:SimulatorRoot
        if ($LASTEXITCODE -ne 0) { throw 'Installing the independent simulator dependencies failed.' }
        Write-Host 'Installed simulator/.venv. Run check.ps1, then start.ps1 without -Install to start services.'
        exit 0
    }

    if ($BrokerOnly -and ($VideoOnly -or $VideoFile -or $EnableUdpSender -or $EnableReceiver)) {
        throw '-BrokerOnly cannot be combined with simulator/video options.'
    }
    if ($VideoOnly -and -not $VideoFile) { throw '-VideoOnly requires -VideoFile.' }
    if (-not $BrokerOnly) {
        if (-not (Test-Path -LiteralPath $script:VenvPython -PathType Leaf)) {
            throw 'Simulator environment missing. Run simulator/scripts/start.ps1 -Install first.'
        }
        & $script:VenvPython -m simulator.server.main --check
        if ($LASTEXITCODE -ne 0) { throw 'Simulator dependency/asset check failed.' }
        if (-not $VideoOnly) { Assert-WebPortFree $WebPort }
        if ($VideoFile) {
            if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
                throw 'FFmpeg is required for -VideoFile. Add ffmpeg to PATH before starting.'
            }
            if (-not [IO.Path]::IsPathRooted($VideoFile)) {
                $VideoFile = Join-Path $script:SimulatorRoot $VideoFile
            }
            if (-not (Test-Path -LiteralPath $VideoFile -PathType Leaf)) {
                throw "Video input does not exist: $VideoFile"
            }
            $VideoFile = (Resolve-Path -LiteralPath $VideoFile).Path
        }
    }

    $lock = Open-SimulatorLock
    try {
        $state = Read-SimulatorState
        $liveProcesses = @($state.processes | Where-Object { $null -ne (Get-OwnedProcess $_) })
        if ($liveProcesses.Count -gt 0 -and -not $BrokerOnly) {
            throw 'This workspace already has owned simulator processes. Run stop.ps1 before starting another session.'
        }
        $state.processes = $liveProcesses
        $startedProcesses = @()
        $startedBroker = $null
        try {
            if (Test-MqttBroker $MqttHost $MqttPort) {
                Write-Host "Reusing MQTT broker at ${MqttHost}:$MqttPort; its ownership is unchanged."
            } else {
                if ($MqttHost -notin @('127.0.0.1','localhost')) {
                    throw 'The requested remote MQTT broker did not accept an MQTT connection. It will not be replaced by a local broker.'
                }
                Assert-TcpPortFree $MqttPort 'MQTT'
                $oldPort = $env:RM_SIM_MQTT_PORT
                try {
                    $env:RM_SIM_MQTT_PORT = [string]$MqttPort
                    $before = Get-BrokerContainer
                    if ($before) {
                        $existingContainer = Get-OwnedBroker ([pscustomobject]@{id=$before})
                        if ($null -eq $existingContainer) {
                            throw 'An existing Compose broker belongs to another configuration. It will not be replaced.'
                        }
                        if ($existingContainer.State.Running) {
                            throw 'A Compose broker is already running but does not accept MQTT at the requested endpoint. It will not be recreated or reconfigured.'
                        }
                    }
                    Invoke-SimulatorCompose -ComposeArguments @('up', '-d', 'broker') | Out-Null
                    $containerId = Get-BrokerContainer
                    if (-not $containerId) { throw 'Docker Compose did not return a broker container ID.' }
                    $record = [pscustomobject]@{id = $containerId; project = $script:ComposeProject; service = 'broker'; port = $MqttPort}
                    # A running broker was already handled by the MQTT probe. A
                    # stopped pre-existing container can be reused without claiming it.
                    if (-not $before -or ($null -ne $state.broker -and $state.broker.id -eq $containerId)) {
                        $startedBroker = $record
                        $state.broker = $record
                        Write-SimulatorState $state
                    } else {
                        Write-Host 'Reused a pre-existing broker container; stop.ps1 will leave it running.'
                    }
                    $ready = $false
                    for ($attempt = 0; $attempt -lt 40; $attempt++) {
                        if (Test-MqttBroker $MqttHost $MqttPort) { $ready = $true; break }
                        Start-Sleep -Milliseconds 250
                    }
                    if (-not $ready) { throw 'Broker did not complete an MQTT handshake before the startup timeout.' }
                } finally { $env:RM_SIM_MQTT_PORT = $oldPort }
            }

            if (-not $BrokerOnly) {
                if (-not $VideoOnly) {
                    $instance = [guid]::NewGuid().ToString('N')
                    $token = [guid]::NewGuid().ToString('N')
                    $arguments = @('simulator.server.main', '--web-host', '127.0.0.1',
                        '--web-port', [string]$WebPort, '--mqtt-host', $MqttHost,
                        '--mqtt-port', [string]$MqttPort, '--target-ip', $TargetIP,
                        '--current-robot-id', [string]$CurrentRobotId)
                    if ($EnableUdpSender) { $arguments += '--enable-udp-sender' }
                    if ($EnableReceiver) { $arguments += '--enable-receiver' }
                    $record = Start-OwnedPython -Role 'server' -Arguments $arguments `
                        -InstanceId $instance -ShutdownToken $token -WebPort $WebPort
                    $startedProcesses += $record
                    $state.processes = @($state.processes) + @($record)
                    Write-SimulatorState $state
                    $ready = $false
                    for ($attempt = 0; $attempt -lt 100; $attempt++) {
                        if ($null -eq (Get-OwnedProcess $record)) { break }
                        $health = Get-SimulatorHealth $WebPort
                        if ($null -ne $health -and $health.instanceId -eq $instance) { $ready = $true; break }
                        Start-Sleep -Milliseconds 200
                    }
                    if (-not $ready) { throw "Simulator did not become healthy. Inspect $($record.stderr) and $($record.stdout)." }
                    Write-Host "Simulator ready: http://127.0.0.1:$WebPort (PID $($record.pid))"
                }
                if ($VideoFile) {
                    $record = Start-OwnedPython -Role 'video' `
                        -Arguments @('simulator.tools.video_sender', $VideoFile, $TargetIP, '3334') `
                        -InstanceId ([guid]::NewGuid().ToString('N')) -ShutdownToken '' -WebPort 0
                    $startedProcesses += $record
                    $state.processes = @($state.processes) + @($record)
                    Write-SimulatorState $state
                    Start-Sleep -Milliseconds 1200
                    if ($null -eq (Get-OwnedProcess $record)) {
                        throw "Video sender exited during startup. Inspect $($record.stderr) and $($record.stdout)."
                    }
                    Write-Host "HEVC UDP video sender ready: ${TargetIP}:3334 (PID $($record.pid))"
                }
            }
            Write-SimulatorState $state
            Write-Host "MQTT ready: ${MqttHost}:$MqttPort. Stop only this session with simulator/scripts/stop.ps1."
        } catch {
            $failure = $_
            # Roll back exactly the resources started by this invocation.
            $stoppedIds = @()
            foreach ($record in @($startedProcesses | Sort-Object -Property role -Descending)) {
                try {
                    Stop-OwnedProcess $record
                    if ($null -eq (Get-OwnedProcess $record)) { $stoppedIds += $record.pid }
                    else { Write-Warning "Owned $($record.role) is still running; its record was retained." }
                } catch { Write-Warning $_ }
            }
            $state.processes = @($state.processes | Where-Object { $_.pid -notin $stoppedIds })
            if ($null -ne $startedBroker) {
                try {
                    Stop-OwnedBroker $startedBroker | Out-Null
                    if ($null -ne $state.broker -and $state.broker.id -eq $startedBroker.id) { $state.broker = $null }
                } catch { Write-Warning $_ }
            }
            Write-SimulatorState $state
            throw $failure
        }
    } finally { $lock.Dispose() }
} finally { Pop-Location }
