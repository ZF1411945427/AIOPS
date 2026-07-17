$ErrorActionPreference = 'SilentlyContinue'
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*run.py*' }
foreach ($p in $procs) {
    Write-Host "=== PID $($p.ProcessId) ==="
    Write-Host "Cmd: $($p.CommandLine)"
    $parent = (Get-CimInstance Win32_Process -Filter "ProcessId=$($p.ProcessId)").ParentProcessId
    Write-Host "Parent PID: $parent"
    if ($parent -ne 0) {
        $parentProc = Get-CimInstance Win32_Process -Filter "ProcessId=$parent"
        Write-Host "Parent Path: $($parentProc.CommandLine)"
    }
    Write-Host ""
}
