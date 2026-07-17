$ErrorActionPreference = 'SilentlyContinue'
$portInfo = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -Unique -ExpandProperty OwningProcess
foreach ($pid in $portInfo) {
    if ($pid -ne 0) {
        Write-Host "PID: $pid"
        Write-Host "CmdLine: $((Get-CimInstance Win32_Process -Filter "ProcessId=$pid").CommandLine)"
    }
}
