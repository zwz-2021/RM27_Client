#requires -Version 5.1
# Drive only the production window with the unique title supplied by the test.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ConfigFile,
    [Parameter(Mandatory)][string]$WindowTitle,
    [Parameter(Mandatory)][ValidateSet('save', 'reopen')][string]$Phase,
    [ValidateSet('Debug', 'Release')][string]$Configuration = 'Debug'
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class ReceiverWindowKeys {
    [DllImport("user32.dll")]
    public static extern IntPtr SendMessage(IntPtr window, int message, IntPtr key, IntPtr data);
}
'@
$evidence = Split-Path -Parent $ConfigFile
$log = Join-Path $evidence "$Phase-window.jsonl"
$utf8 = New-Object System.Text.UTF8Encoding($false)

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

function Wait-View([string]$Description, [scriptblock]$Condition) {
    $timer = [Diagnostics.Stopwatch]::StartNew()
    do {
        $all = Get-Controls
        $text = @{}
        foreach ($name in @('connectionValue', 'identityValue', 'seatLabel', 'healthValue',
                'configFeedbackLabel', 'actionFeedbackLabel', 'diagnosticLabel')) {
            if ($all.ContainsKey($name)) { $text[$name] = $all[$name].Current.Name }
        }
        foreach ($name in @('receiverRobotBox', 'saveReceiverButton')) {
            $text[$name] = $all.ContainsKey($name) -and $all[$name].Current.IsEnabled
        }
        if (& $Condition $text) {
            $text['observation'] = $Description
            [IO.File]::AppendAllText($log, (ConvertTo-Json $text -Compress) + [Environment]::NewLine, $utf8)
            return
        }
        Start-Sleep -Milliseconds 100
    } while ($timer.Elapsed.TotalSeconds -lt 12)
    throw "$Description timed out. Last view: $(ConvertTo-Json $text -Compress)"
}

function Invoke-Control([string]$Name) {
    $element = (Get-Controls)[$Name]
    if (-not $element -or -not $element.Current.IsEnabled) { throw "$Name is unavailable" }
    $element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
}

function Select-BlueThree {
    # Target Qt's own focused combo and HWND. No input goes to the user's active application.
    (Get-Controls)['receiverRobotBox'].SetFocus()
    # Both stops follow a red 3 session. Advance to the same position in the blue team.
    for ($i = 0; $i -lt 8; $i++) {
        [void][ReceiverWindowKeys]::SendMessage($client.MainWindowHandle, 0x100, [IntPtr]0x28, [IntPtr]0)
        [void][ReceiverWindowKeys]::SendMessage($client.MainWindowHandle, 0x101, [IntPtr]0x28, [IntPtr]0)
    }
}

function Stop-Receiving {
    Invoke-Control 'stopButton'
    Wait-View 'stopped with empty data and editable selection' {
        param($v)
        $v.connectionValue -eq '已停止' -and $v.healthValue -eq '—' -and $v.receiverRobotBox
    }
}

function Wait-Receiving([int]$Robot, [string]$Health, [string]$Seat) {
    Wait-View "receive as $Robot, HP $Health and read-only seat" {
        param($v)
        $v.connectionValue -eq '五类订阅就绪' -and $v.seatLabel -eq $Seat -and
        $v.identityValue -match "\b$Robot\b" -and $v.healthValue -eq $Health -and
        -not $v.receiverRobotBox -and -not $v.saveReceiverButton
    }
}

$entry = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts/run.ps1'
$launcher = Start-Process powershell.exe -PassThru -WindowStyle Hidden -ArgumentList @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $entry + '"'), '-SkipBuild',
    '-Configuration', $Configuration, '-ConfigFile', ('"' + $ConfigFile + '"'),
    '-LogDirectory', ('"' + $evidence + '"'))
$client = $null
try {
    $timer = [Diagnostics.Stopwatch]::StartNew()
    while (-not $client -and -not $launcher.HasExited -and $timer.Elapsed.TotalSeconds -lt 15) {
        $client = Get-Process -Name RM27_Client -ErrorAction SilentlyContinue |
            Where-Object { $_.MainWindowTitle -eq $WindowTitle } | Select-Object -First 1
        if (-not $client) { Start-Sleep -Milliseconds 100 }
    }
    if (-not $client) { throw "No product window for $WindowTitle" }
    $infantry = '本地席位 · 步兵（只读）'
    $legacy = '本地席位 · 未指定（只读）'
    if ($Phase -eq 'save') {
        Wait-Receiving 3 '321' $legacy
        Stop-Receiving
        Select-BlueThree
        $original = [Convert]::ToBase64String([IO.File]::ReadAllBytes($ConfigFile))
        # Allow reads but deny atomic replacement while the save button is exercised.
        $held = [IO.File]::Open($ConfigFile, 'Open', 'Read', 'Read')
        try {
            Invoke-Control 'saveReceiverButton'
            Wait-View 'failed save explains the error and preserves the old seat' {
                param($v)
                $v.configFeedbackLabel -match '失败|无法|不能' -and $v.seatLabel -eq $legacy
            }
            if ([Convert]::ToBase64String([IO.File]::ReadAllBytes($ConfigFile)) -ne $original) {
                throw 'Failed save changed the original file'
            }
        } finally { $held.Dispose() }
        Invoke-Control 'startButton'
        Wait-Receiving 3 '321' $legacy
        Stop-Receiving
        Select-BlueThree
        Invoke-Control 'saveReceiverButton'
        Wait-View 'saved new seat and ID while stopped' {
            param($v)
            $v.configFeedbackLabel -match '已保存|保存成功' -and $v.seatLabel -eq $infantry -and
            $v.connectionValue -eq '已停止' -and $v.healthValue -eq '—'
        }
        Invoke-Control 'startButton'
    } else {
        Wait-View 'reopened client rejects previous robot data' {
            param($v)
            $v.diagnosticLabel -match '配置机器人 103，收到 3' -and $v.identityValue -eq '—' -and
            $v.healthValue -eq '—' -and $v.seatLabel -eq $infantry
        }
        [IO.File]::WriteAllText((Join-Path $evidence 'allow-matching-data.flag'), '103')
    }
    Wait-Receiving 103 '322' $infantry
    Invoke-Control 'competitionActionButton'
    Wait-View 'infantry action explains local refusal' { param($v) $v.actionFeedbackLabel -match '步兵席只读' }
    if ($Phase -eq 'reopen') {
        [IO.File]::WriteAllText((Join-Path $evidence 'stop-test-broker.flag'), 'stop')
        Wait-View 'waiting for reconnect clears old data and disables editing' {
            param($v)
            $v.connectionValue -eq '等待重连' -and $v.healthValue -eq '—' -and $v.identityValue -eq '—' -and
            -not $v.receiverRobotBox -and -not $v.saveReceiverButton
        }
        Stop-Receiving
    }
} catch {
    [IO.File]::WriteAllText((Join-Path $evidence "$Phase-error.txt"), "$($_.Exception.Message)`n$($_.ScriptStackTrace)", $utf8)
    throw
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
    if ($client) {
        if (-not $client.HasExited) { throw "Product PID $($client.Id) still active" }
        $closed = @{ observation = 'closed'; productPid = $client.Id; launcherPid = $launcher.Id }
        [IO.File]::AppendAllText($log, (ConvertTo-Json $closed -Compress) + [Environment]::NewLine, $utf8)
    }
}
