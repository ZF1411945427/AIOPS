try {
    $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/ansible/api/status' -UseBasicParsing -TimeoutSec 5
    Write-Output "STATUS: $($r.Content)"
} catch {
    Write-Output "ERR: $($_.Exception.Message)"
}
