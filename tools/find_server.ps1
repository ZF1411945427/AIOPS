$ErrorActionPreference = 'SilentlyContinue'
$portInfo = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -Unique -ExpandProperty OwningProcess
foreach ($pid in $portInfo) {
    if ($pid -ne 0) {
        $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
        $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId=$pid").CommandLine
        Write-Host "PID: $pid"
        Write-Host "Process: $($proc.Path)"
        Write-Host "CommandLine: $cmdLine"
        Write-Host "Parent: $((Get-CimInstance Win32_Process -Filter "ProcessId=$pid").ParentProcessId)"
    }
}
