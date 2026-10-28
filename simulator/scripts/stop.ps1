[CmdletBinding()]
param([switch]$KeepBroker)

. (Join-Path $PSScriptRoot 'common.ps1')
$lock = Open-SimulatorLock
try {
    $state = Read-SimulatorState
    $remaining = @()
    foreach ($record in @($state.processes | Sort-Object -Property role -Descending)) {
        try { Stop-OwnedProcess $record }
        catch {
            $remaining += $record
            Write-Warning "Could not stop owned $($record.role): $_"
        }
    }
    $state.processes = $remaining
    $brokerFailure = $null
    if (-not $KeepBroker -and $null -ne $state.broker) {
        try {
            Stop-OwnedBroker $state.broker | Out-Null
            $state.broker = $null
        } catch { $brokerFailure = $_ }
    }
    Write-SimulatorState $state
    if ($null -ne $brokerFailure) { throw $brokerFailure }
    if ($remaining.Count -gt 0) { throw 'Some owned processes could not be stopped; their ownership records were preserved.' }
    Write-Host 'Owned simulator processes stopped. Reused brokers and unrelated processes were left alone.'
} finally { $lock.Dispose() }
