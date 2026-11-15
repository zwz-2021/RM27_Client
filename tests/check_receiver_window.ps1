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
. (Join-Path $PSScriptRoot 'qt_window_helpers.ps1')
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

function Test-ProfileWindow($client) {
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
}

try {
    $closed = Invoke-ProductWindow $ConfigFile $WindowTitle $Configuration $evidence ${function:Test-ProfileWindow}
    [IO.File]::AppendAllText($log, (ConvertTo-Json $closed -Compress) + [Environment]::NewLine, $utf8)
} catch {
    [IO.File]::WriteAllText((Join-Path $evidence "$Phase-error.txt"), "$($_.Exception.Message)`n$($_.ScriptStackTrace)", $utf8)
    throw
}
