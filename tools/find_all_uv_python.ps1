$ErrorActionPreference = 'SilentlyContinue'
$pythonProcs = Get-Process python* | Where-Object { $_.Path -like '*\AppData\Roaming\uv\python\*' }
foreach ($p in $pythonProcs) {
    Write-Host "=== PID $($p.Id) ==="
    Write-Host "Path: $($p.Path)"
    Write-Host "Parent: $((Get-CimInstance Win32_Process -Filter "ProcessId=$($p.Id)").ParentProcessId)"
    Write-Host "CmdLine: $((Get-CimInstance Win32_Process -Filter "ProcessId=$($p.Id)").CommandLine)"
    Write-Host ""
}
