# Simulator-only helpers. Compatible with Windows PowerShell 5.1 and PowerShell 7.
$ErrorActionPreference = 'Stop'
$script:SimulatorRoot = Split-Path -Parent $PSScriptRoot
$script:RepositoryRoot = Split-Path -Parent $script:SimulatorRoot
$script:RuntimeRoot = Join-Path $script:SimulatorRoot '.runtime'
$script:StatePath = Join-Path $script:RuntimeRoot 'state.json'
$script:ComposeFile = Join-Path $script:SimulatorRoot 'docker-compose.yml'
$script:VenvPython = Join-Path $script:SimulatorRoot '.venv\Scripts\python.exe'
$script:ComposeProject = 'rm27-simulator'

function Open-SimulatorLock {
    New-Item -ItemType Directory -Path $script:RuntimeRoot -Force | Out-Null
    try {
        return [IO.File]::Open((Join-Path $script:RuntimeRoot 'lifecycle.lock'),
            [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    } catch { throw 'Another simulator start/stop operation is active. Retry after it finishes.' }
}

function Read-SimulatorState {
    if (Test-Path -LiteralPath $script:StatePath) {
        $state = Get-Content -LiteralPath $script:StatePath -Raw | ConvertFrom-Json
        if ($state.version -ne 1 -or $state.root -ne $script:SimulatorRoot) {
            throw 'The simulator ownership record belongs to another workspace or version.'
        }
        return $state
    }
    return [pscustomobject]@{version = 1; root = $script:SimulatorRoot; processes = @(); broker = $null}
}

function Write-SimulatorState($State) {
    $temporary = Join-Path $script:RuntimeRoot ('state-' + [guid]::NewGuid().ToString('N') + '.tmp')
    $json = $State | ConvertTo-Json -Depth 8
    [IO.File]::WriteAllText($temporary, $json, (New-Object Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $temporary -Destination $script:StatePath -Force
}

function Test-MqttBroker([string]$Address, [int]$Port) {
    $connection = New-Object Net.Sockets.TcpClient
    try {
        $attempt = $connection.ConnectAsync($Address, $Port)
        if (-not $attempt.Wait(1500)) { return $false }
        if (-not $connection.Connected) { return $false }
        $stream = $connection.GetStream()
        $stream.ReadTimeout = 1500
        $stream.WriteTimeout = 1500
        [byte[]]$connect = @(0x10,0x12,0,4,77,81,84,84,4,2,0,5,0,6,114,109,50,55,112,115)
        $stream.Write($connect, 0, $connect.Length)
        [byte[]]$acknowledgement = @(0,0,0,0)
        $received = 0
        while ($received -lt 4) {
            $count = $stream.Read($acknowledgement, $received, 4 - $received)
            if ($count -eq 0) { return $false }
            $received += $count
        }
        return ($acknowledgement[0] -eq 0x20 -and $acknowledgement[1] -eq 2 -and
            $acknowledgement[2] -eq 0 -and $acknowledgement[3] -eq 0)
    } catch { return $false }
    finally { $connection.Dispose() }
}

function Assert-TcpPortFree([int]$Port, [string]$Purpose) {
    $listener = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback, $Port)
    try { $listener.Start() }
    catch { throw "$Purpose port $Port is occupied. Choose another port or stop its owner yourself." }
    finally { $listener.Stop() }
}

function Assert-WebPortFree([int]$Port) { Assert-TcpPortFree $Port 'Web' }

function Get-SimulatorHealth([int]$Port) {
    try { return Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 2 }
    catch { return $null }
}

function Get-OwnedProcess($Record) {
    if ($null -eq $Record -or [int]$Record.pid -le 0) { return $null }
    $process = Get-Process -Id ([int]$Record.pid) -ErrorAction SilentlyContinue
    if ($null -eq $process) { return $null }
    try {
        if ($process.StartTime.ToUniversalTime().Ticks.ToString() -ne [string]$Record.startTicks) { return $null }
        if ($process.Path -ne [string]$Record.executable) { return $null }
        return $process
    } catch { return $null }
}

function Start-OwnedPython([string]$Role, [string[]]$Arguments, [string]$InstanceId,
                           [string]$ShutdownToken, [int]$WebPort) {
    $identity = [guid]::NewGuid().ToString('N')
    $stdout = Join-Path $script:RuntimeRoot "$Role-$identity.log"
    $stderr = Join-Path $script:RuntimeRoot "$Role-$identity.error.log"
    $spawnRequest = Join-Path $script:RuntimeRoot "spawn-$identity.json"
    $request = @{arguments = $Arguments; cwd = $script:RepositoryRoot; stdout = $stdout; stderr = $stderr}
    [IO.File]::WriteAllText($spawnRequest, ($request | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding($false)))
    $oldInstance = $env:RM_SIM_INSTANCE_ID
    $oldToken = $env:RM_SIM_SHUTDOWN_TOKEN
    $oldUtf8 = $env:PYTHONUTF8
    $oldHostRecord = $env:RM_SIM_HOST_RECORD
    $hostRecord = Join-Path $script:RuntimeRoot "host-$identity.json"
    try {
        $env:RM_SIM_INSTANCE_ID = $InstanceId
        $env:RM_SIM_SHUTDOWN_TOKEN = $ShutdownToken
        $env:PYTHONUTF8 = '1'
        $env:RM_SIM_HOST_RECORD = $hostRecord
        # Popen(close_fds=True) prevents detached children inheriting an IDE or
        # test's captured PowerShell pipes. JobObject ownership is set in host.
        $launchJson = & $script:VenvPython -m simulator.scripts.process_host --spawn $spawnRequest
        if ($LASTEXITCODE -ne 0) { throw 'The detached Python launcher failed.' }
        $launchIdentity = $launchJson | ConvertFrom-Json
        $process = Get-Process -Id ([int]$launchIdentity.pid) -ErrorAction Stop
        $launcher = [pscustomobject]@{pid=$process.Id; executable=$process.Path;
            startTicks=$process.StartTime.ToUniversalTime().Ticks.ToString()}
        # Windows venv python.exe can be a redirector that waits for a second
        # interpreter. Record the actual JobObject host, not that redirector.
        for ($attempt = 0; $attempt -lt 100 -and -not (Test-Path -LiteralPath $hostRecord); $attempt++) {
            if ($process.HasExited) { break }
            Start-Sleep -Milliseconds 50
        }
        if (-not (Test-Path -LiteralPath $hostRecord)) {
            $ownedLauncher = Get-OwnedProcess $launcher
            if ($null -ne $ownedLauncher) { Stop-Process -Id $ownedLauncher.Id -Force }
            throw "Python host failed before reporting ownership. Inspect $stderr and $stdout."
        }
        $hostIdentity = Get-Content -LiteralPath $hostRecord -Raw | ConvertFrom-Json
        if ($hostIdentity.instanceId -ne $InstanceId) { throw 'Python host ownership handshake did not match.' }
        $hostProcess = Get-Process -Id ([int]$hostIdentity.pid) -ErrorAction Stop
        if ($hostProcess.Id -eq $process.Id) { $launcher = $null }
        return [pscustomobject]@{
            role = $Role; pid = $hostProcess.Id
            startTicks = $hostProcess.StartTime.ToUniversalTime().Ticks.ToString()
            executable = $hostProcess.Path; instanceId = $InstanceId; launcher=$launcher
            shutdownToken = $ShutdownToken; webPort = $WebPort
            stdout = $stdout; stderr = $stderr
        }
    } finally {
        $env:RM_SIM_INSTANCE_ID = $oldInstance
        $env:RM_SIM_SHUTDOWN_TOKEN = $oldToken
        $env:PYTHONUTF8 = $oldUtf8
        $env:RM_SIM_HOST_RECORD = $oldHostRecord
        [IO.File]::Delete($spawnRequest)
    }
}

function Stop-OwnedProcess($Record) {
    $process = Get-OwnedProcess $Record
    if ($null -eq $process) {
        Write-Host "No matching owned $($Record.role) process; nothing will be terminated."
        return
    }
    if ($Record.role -eq 'server') {
        $health = Get-SimulatorHealth ([int]$Record.webPort)
        if ($null -ne $health -and $health.instanceId -eq $Record.instanceId) {
            try {
                Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$($Record.webPort)/api/shutdown" `
                    -Headers @{'X-Simulator-Token' = $Record.shutdownToken} -TimeoutSec 2 | Out-Null
            } catch { Write-Host 'Graceful shutdown was unavailable; checking the owned process again.' }
            $process.WaitForExit(8000) | Out-Null
        }
    }
    # Revalidate PID, start time and executable immediately before termination.
    $matching = Get-OwnedProcess $Record
    if ($null -ne $matching) {
        Stop-Process -Id $matching.Id -Force -ErrorAction Stop
        $matching.WaitForExit(5000) | Out-Null
    }
    if ($null -ne $Record.launcher) {
        $launcher = Get-OwnedProcess $Record.launcher
        if ($null -ne $launcher) {
            $launcher.WaitForExit(2000) | Out-Null
            $launcher = Get-OwnedProcess $Record.launcher
            if ($null -ne $launcher) { Stop-Process -Id $launcher.Id -Force }
        }
    }
}

function Invoke-SimulatorCompose([string[]]$ComposeArguments) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker is required to start the standalone broker. Install/start Docker Desktop or reuse an existing MQTT broker.'
    }
    $result = & docker compose --project-directory $script:SimulatorRoot -f $script:ComposeFile `
        -p $script:ComposeProject @ComposeArguments
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed: $($ComposeArguments -join ' ')" }
    return $result
}

function Get-BrokerContainer {
    $result = Invoke-SimulatorCompose -ComposeArguments @('ps', '-aq', 'broker')
    $identifier = (@($result) -join '').Trim()
    if (-not $identifier) { return $null }
    return $identifier
}

function Get-OwnedBroker($Record) {
    if ($null -eq $Record -or -not (Get-Command docker -ErrorAction SilentlyContinue)) { return $null }
    try {
        $raw = & docker inspect ([string]$Record.id) 2>$null
        if ($LASTEXITCODE -ne 0) { return $null }
        $container = @($raw | ConvertFrom-Json)[0]
        $labels = $container.Config.Labels
        $configuration = [string]$labels.'com.docker.compose.project.config_files'
        if ($container.Id -ne $Record.id -or
            $labels.'com.docker.compose.project' -ne $script:ComposeProject -or
            $labels.'com.docker.compose.service' -ne 'broker' -or
            $configuration.Replace('\','/').ToLowerInvariant() -ne $script:ComposeFile.Replace('\','/').ToLowerInvariant()) {
            return $null
        }
        return $container
    } catch { return $null }
}

function Stop-OwnedBroker($Record) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker is unavailable; the owned broker could not be inspected or stopped. Its ownership record must be retained.'
    }
    $container = Get-OwnedBroker $Record
    if ($null -eq $container) {
        & docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw 'Docker daemon is unavailable; the owned broker could not be inspected or stopped. Its ownership record must be retained.'
        }
        Write-Host 'No matching script-owned broker container; no container will be stopped.'
        return $true
    }
    if ($container.State.Running) {
        & docker stop --time 5 ([string]$Record.id) | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Could not stop the owned broker container.' }
    }
    return $true
}
