#requires -Version 5.1
# The Python test sends one action per line. EOF closes this test's own window.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ConfigFile,
    [Parameter(Mandatory)][string]$WindowTitle,
    [ValidateSet('Debug', 'Release')][string]$Configuration = 'Debug'
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'qt_window_helpers.ps1')
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$directory = Split-Path -Parent $ConfigFile
$closed = Invoke-ProductWindow $ConfigFile $WindowTitle $Configuration $directory {
    param($client)
    [Console]::WriteLine('{"ready":true}')
    while ($null -ne ($action = [Console]::ReadLine())) {
        switch ($action) {
            'snapshot' {
                $view = @{}
                $controls = Get-Controls
                foreach ($id in @('connectionValue', 'seatLabel', 'identityValue', 'healthValue',
                                   'udpBindingLabel', 'udpCountersLabel', 'udpHeaderLabel',
                                   'udpAssemblyLabel', 'udpLastFrameLabel')) {
                    if ($controls.ContainsKey($id)) { $view[$id] = $controls[$id].Current.Name }
                }
                [Console]::WriteLine((ConvertTo-Json $view -Compress))
            }
            { $_ -in @('overviewTab', 'diagnosticsTab', 'stopButton', 'startButton') } {
                Invoke-Control $action
                [Console]::WriteLine('{"invoked":true}')
            }
            default { throw "Unknown test action: $action" }
        }
    }
}
[Console]::WriteLine((ConvertTo-Json $closed -Compress))
