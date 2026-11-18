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
                                   'udpBindingLabel', 'udpCountersLabel', 'udpHeaderLabel', 'udpPacketAgeLabel', 'udpPacketRateLabel',
                                   'udpFrameRateLabel', 'udpAssemblyLabel', 'udpLastFrameLabel', 'videoDecodeLabel', 'videoPreviewStatus')) {
                    if ($controls.ContainsKey($id)) { $view[$id] = $controls[$id].Current.Name }
                }
                [Console]::WriteLine((ConvertTo-Json $view -Compress))
            }
            { $_ -in @('capturePreview', 'captureDiagnostics') } {
                if (-not (Get-Command Save-PreviewCapture -ErrorAction SilentlyContinue)) {
                    . (Join-Path $PSScriptRoot 'capture_qt_preview.ps1')
                }
                if ($action -eq 'captureDiagnostics') {
                    $capture = Save-PreviewCapture $client.MainWindowHandle (Join-Path $directory 'udp-silence.png') -WholeWindow
                } else {
                    $capture = Save-PreviewCapture $client.MainWindowHandle (Join-Path $directory 'capture.png')
                }
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
