#requires -Version 5.1
# The Python test sends one action per line. EOF closes this test's own window.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ConfigFile,
    [Parameter(Mandatory)][string]$WindowTitle,
    [ValidateSet('Debug', 'Release')][string]$Configuration = 'Debug',
    [switch]$TraceSimulatedVideo
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
                                   'udpAssemblyLabel', 'udpLastFrameLabel', 'videoDecodeLabel', 'videoPreviewStatus')) {
                    if ($controls.ContainsKey($id)) { $view[$id] = $controls[$id].Current.Name }
                }
                [Console]::WriteLine((ConvertTo-Json $view -Compress))
            }
            'capturePreview' {
                if (-not (Get-Command Save-PreviewCapture -ErrorAction SilentlyContinue)) {
                    . (Join-Path $PSScriptRoot 'capture_qt_preview.ps1')
                }
                $surface = (Get-Controls)['videoPreviewSurface']
                if (-not $surface) { throw 'Missing preview surface in the workbench' }
                $capture = Save-PreviewCapture $client.MainWindowHandle $surface.Current.BoundingRectangle `
                    (Join-Path $directory 'capture.png')
                [Console]::WriteLine((ConvertTo-Json $capture -Depth 4 -Compress))
            }
            { $_ -in @('overviewTab', 'diagnosticsTab', 'stopButton', 'startButton', 'saveReceiverButton') } {
                Invoke-Control $action
                [Console]::WriteLine('{"invoked":true}')
            }
            default { throw "Unknown test action: $action" }
        }
    }
} -TraceSimulatedVideo:$TraceSimulatedVideo
[Console]::WriteLine((ConvertTo-Json $closed -Compress))
