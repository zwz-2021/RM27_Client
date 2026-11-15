#requires -Version 5.1
Add-Type -AssemblyName UIAutomationClient

function Get-Controls {
    $query = [Diagnostics.Stopwatch]::StartNew()
    while ($true) {
        try {
            $items = @{}
            $client.Refresh()
            $window = [System.Windows.Automation.AutomationElement]::FromHandle($client.MainWindowHandle)
            foreach ($element in $window.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                     [System.Windows.Automation.Condition]::TrueCondition)) {
                $id = $element.Current.AutomationId
                if ($id) { $items[$id.Split('.')[-1]] = $element }
            }
            return $items
        } catch [System.Windows.Automation.ElementNotAvailableException], [Runtime.InteropServices.COMException] {
            # Qt may rebuild the accessibility tree when a feedback label appears or disappears.
            if ($query.Elapsed.TotalSeconds -ge 2) { throw }
            Start-Sleep -Milliseconds 50
        }
    }
}

function Invoke-Control([string]$Name) {
    $element = (Get-Controls)[$Name]
    if (-not $element -or -not $element.Current.IsEnabled) { throw "$Name is unavailable" }
    $element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
}

function Invoke-ProductWindow([string]$ConfigFile, [string]$WindowTitle, [string]$Configuration,
                              [string]$LogDirectory, [scriptblock]$Exercise) {
    $entry = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts/run.ps1'
    $launcher = Start-Process powershell.exe -PassThru -WindowStyle Hidden -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $entry + '"'), '-SkipBuild',
        '-Configuration', $Configuration, '-ConfigFile', ('"' + $ConfigFile + '"'),
        '-LogDirectory', ('"' + $LogDirectory + '"'))
    $client = $null
    try {
        $timer = [Diagnostics.Stopwatch]::StartNew()
        while (-not $client -and -not $launcher.HasExited -and $timer.Elapsed.TotalSeconds -lt 15) {
            $client = Get-Process -Name RM27_Client -ErrorAction SilentlyContinue |
                Where-Object { $_.MainWindowTitle -eq $WindowTitle } | Select-Object -First 1
            if (-not $client) { Start-Sleep -Milliseconds 100 }
        }
        if (-not $client) { throw "No product window for $WindowTitle" }
        & $Exercise $client
    } finally {
        if (-not $client -and -not $launcher.HasExited) {
            # An invalid config may leave a window with the default title. Scope cleanup to this launcher.
            $child = Get-CimInstance Win32_Process -Filter "Name='RM27_Client.exe' AND ParentProcessId=$($launcher.Id)" |
                Select-Object -First 1
            if ($child) { $client = Get-Process -Id $child.ProcessId -ErrorAction SilentlyContinue }
        }
        if ($client -and -not $client.HasExited) { [void]$client.CloseMainWindow() }
        if (-not $launcher.WaitForExit(7000)) {
            if ($client -and -not $client.HasExited) { $client.Kill() }
            $launcher.Kill()
            throw 'Product failed to exit normally'
        }
        if ($launcher.ExitCode -ne 0) { throw "Launcher returned $($launcher.ExitCode)" }
        if ($client -and -not $client.HasExited) { throw "Product PID $($client.Id) still active" }
    }
    return @{ observation = 'closed'; productPid = $client.Id; launcherPid = $launcher.Id }
}
