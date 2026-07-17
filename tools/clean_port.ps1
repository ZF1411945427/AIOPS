$ErrorActionPreference = 'SilentlyContinue'
$portInfo = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($portInfo) {
    $pids = $portInfo | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($pid in $pids) {
        if ($pid -ne 0) {
            Stop-Process -Id $pid -Force
            Write-Host "Killed PID $pid"
        }
    }
}
Start-Sleep 3
$remaining = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess
Write-Host "Remaining: $remaining"
