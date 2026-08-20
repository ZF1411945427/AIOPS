<#
.SYNOPSIS
opencode 会话进程清理脚本 — 排查并清理因历史会话/进程堆叠导致的内存卡顿。

.DESCRIPTION
实时扫描所有 opencode 进程(server + 语言服务器 LSP 子进程),按内存占用排序展示,
并可安全清理"无响应的死进程"(HTTP 探测失败)来释放内存,避免卡顿。

本脚本默认【只清理无响应的死进程】,绝不杀掉正在承载活跃会话的 server 进程,
因此不会误杀你正在使用中的会话。所有杀进程操作都有交互确认,符合高危操作必审规范。

.PARAMETER status
(默认) 仅列出所有 opencode 进程及其内存/子进程/响应状态,不做任何修改。

.PARAMETER clean
清扫无响应的死进程(HTTP 探测失败的那些),逐个展示并等待确认后强杀。
保留所有活跃 server 进程。

.PARAMETER force
强制按指定 PID 清理,可传多个 PID(以空格分隔)。会先展示目标再需确认。

.PARAMETER CleanBak
同时删除 opencode.db.bak 备份文件(释放磁盘,仅当存在时询问)。

.EXAMPLE
powershell -ExecutionPolicy Bypass -File tools\clean_opencode_sessions.ps1 status
powershell -ExecutionPolicy Bypass -File tools\clean_opencode_sessions.ps1 clean
powershell -ExecutionPolicy Bypass -File tools\clean_opencode_sessions.ps1 force 1234 5678
powershell -ExecutionPolicy Bypass -File tools\clean_opencode_sessions.ps1 clean -CleanBak
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('status', 'clean', 'force')]
    [string]$Action = 'status',

    [Parameter()]
    [string[]]$PIDList = @(),

    [Parameter()]
    [switch]$CleanBak
)

$ErrorActionPreference = 'Continue'

# ---------- 工具函数 ----------
function Write-Step($msg) {
    Write-Host ""
    Write-Host "==== $msg ====" -ForegroundColor Cyan
}

function Get-TotalMemMB([long]$bytes) {
    return [math]::Round($bytes / 1MB)
}

function Confirm-Kill($label, $pid, $memMB, $cpuSec) {
    Write-Host ""
    Write-Host ("  将强制终止进程: PID={0}  内存={1} MB  CPU时间={2}s  <{3}>" -f $pid, $memMB, $cpuSec, $label) -ForegroundColor Yellow
    $ans = Read-Host "  确认终止? [y/N]"
    if ($ans -match '^(y|Y|yes)$') {
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        Write-Host "  => 已终止 PID $pid" -ForegroundColor Green
        return $true
    }
    else {
        Write-Host "  => 跳过 PID $pid" -ForegroundColor DarkGray
        return $false
    }
}

# ---------- 收集 opencode 进程树 ----------
function Get-OpencodeProcesses {
    $procs = Get-CimInstance Win32_Process -Filter "Name='opencode.exe'" -ErrorAction SilentlyContinue
    $nodes = @()
    foreach ($p in $procs) {
        $ws = (Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue).WorkingSet64
        $cpu = (Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue).CPU
        $nodes += [PSCustomObject]@{
            PID     = $p.ProcessId
            Parent  = $p.ParentProcessId
            MemMB   = Get-TotalMemMB $ws
            CPUSec  = [math]::Round($cpu, 1)
            IsServer = ($p.CommandLine -match '--port ')
            IsLSP   = ($p.CommandLine -match 'langserver')
            Command = $p.CommandLine
        }
    }
    return $nodes
}

# 探测某个 server 端口是否响应
function Test-ServerAlive($port) {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$port/session" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
        return ($resp.StatusCode -eq 200)
    }
    catch {
        return $false
    }
}

# ---------- 主逻辑 ----------
if ($Action -eq 'status') {
    Write-Step "扫描 opencode 进程 (status: 只读,不修改)"
    $nodes = Get-OpencodeProcesses
    if ($nodes.Count -eq 0) {
        Write-Host "没有发现任何 opencode 进程在运行。" -ForegroundColor Green
    }
    else {
        Write-Host ("共发现 {0} 个 opencode 进程,总内存约 {1} MB" -f $nodes.Count, (($nodes | Measure-Object MemMB -Sum).Sum)) -ForegroundColor Yellow
        Write-Host ""
        $nodes | Sort-Object MemMB -Descending | ForEach-Object {
            $role = if ($_.IsLSP) { 'LSP ' } elseif ($_.IsServer) { 'SRV ' } else { '    ' }
            $port = if ($_.IsServer) { ($_.Command -split '--port ')[1] } else { '    ' }
            $alive = if ($_.IsServer) { (Test-ServerAlive ([int]$port)) } else { 'n/a' }
            Write-Host ("  {0} PID={1,-6} 内存={2,6}MB  CPU={3,8}s  父={4,-6}  活={5}  {6}" -f $role, $_.PID, $_.MemMB, $_.CPUSec, $_.Parent, $alive, $_.Command)
        }
        Write-Host ""
        Write-Host "提示: 运行  clean 可清理 [无响应] 的死进程; force <PID...> 可强制清理指定 PID。" -ForegroundColor DarkGray
    }
}
elseif ($Action -eq 'clean') {
    Write-Step "清扫无响应的死进程 (clean)"
    $nodes = Get-OpencodeProcesses
    if ($nodes.Count -eq 0) {
        Write-Host "没有发现任何 opencode 进程。" -ForegroundColor Green
        return
    }

    # 找出所有 server 端口并探测
    $deadPids = @()
    foreach ($n in $nodes) {
        if ($n.IsServer) {
            $port = [int](($n.Command -split '--port ')[1])
            $alive = Test-ServerAlive $port
            if (-not $alive) {
                $deadPids += $n.PID
            }
        }
    }

    if ($deadPids.Count -eq 0) {
        Write-Host "没有发现无响应的死进程,当前所有 server 都在正常运行。" -ForegroundColor Green
        return
    }

    Write-Host ("发现 {0} 个无响应的死 server 进程,将连同其 LSP 子进程一起清理:" -f $deadPids.Count) -ForegroundColor Yellow
    Write-Host ""

    # 收集死 server 及其子树(子进程)
    $killSet = @{}
    foreach ($pid in $deadPids) {
        $killSet[$pid] = $true
        # 递归找子进程
        $queue = @($pid)
        while ($queue.Count -gt 0) {
            $cur = $queue[0]; $queue = $queue | Select-Object -Skip 1
            foreach ($n in $nodes) {
                if ($n.Parent -eq $cur -and -not $killSet.ContainsKey($n.PID)) {
                    $killSet[$n.PID] = $true
                    $queue += $n.PID
                }
            }
        }
    }

    $toKill = @()
    foreach ($n in $nodes) {
        if ($killSet.ContainsKey($n.PID)) {
            $toKill += $n
        }
    }

    # 展示即将清理的清单,并逐个确认
    Write-Host "● 即将清理的进程清单(全部需确认):"
    $freedMB = 0
    foreach ($n in $toKill) {
        $role = if ($n.IsLSP) { 'LSP' } else { 'SRV' }
        $freedMB += $n.MemMB
    }
    Write-Host ("  预期释放内存约 {0} MB" -f $freedMB) -ForegroundColor Yellow
    Write-Host ""

    foreach ($n in $toKill) {
        $role = if ($n.IsLSP) { 'LSP' } else { 'SRV' }
        Confirm-Kill ("$role " + $n.Command.Substring(0, [math]::Min(60, $n.Command.Length)) + '...') $n.PID $n.MemMB $n.CPUSec
    }

    Write-Host ""
    Write-Host "清理完成。剩余内存占用:" -ForegroundColor Cyan
    $remain = Get-OpencodeProcesses
    if ($remain.Count -gt 0) {
        Write-Host ("  剩余 {0} 个 opencode 进程,约 {1} MB" -f $remain.Count, (($remain | Measure-Object MemMB -Sum).Sum))
    }
    else {
        Write-Host "  无剩余 opencode 进程。"
    }
}
elseif ($Action -eq 'force') {
    Write-Step "强制清理指定 PID (force)"
    if ($PIDList.Count -eq 0) {
        Write-Host "用法: clean_opencode_sessions.ps1 force 1234 5678 ..." -ForegroundColor Yellow
        return
    }
    Write-Host "即将清理以下 PID:$($PIDList -join ', ')" -ForegroundColor Yellow
    foreach ($pid in $PIDList) {
        $p = Get-Process -Id $pid -ErrorAction SilentlyContinue
        if ($p) {
            Confirm-Kill '指定进程' $pid (Get-TotalMemMB $p.WorkingSet64) ([math]::Round($p.CPU, 1))
        }
        else {
            Write-Host "  PID $pid 不存在或已退出,跳过" -ForegroundColor DarkGray
        }
    }
}

# ---------- 可选:清理磁盘备份 ----------
if ($CleanBak) {
    Write-Step "可选:删除 opencode.db.bak 备份"
    $dbDir = Join-Path $env:USERPROFILE '.local\share\opencode'
    $bak = Join-Path $dbDir 'opencode.db.bak'
    if (Test-Path $bak) {
        $sizeMB = Get-TotalMemMB (Get-Item $bak).Length
        Write-Host ("发现备份文件 {0}  ({1} MB)" -f $bak, $sizeMB) -ForegroundColor Yellow
        $ans = Read-Host "删除该备份释放磁盘? [y/N]"
        if ($ans -match '^(y|Y|yes)$') {
            Remove-Item $bak -Force
            Write-Host "  => 已删除 $bak" -ForegroundColor Green
        }
        else {
            Write-Host "  => 跳过" -ForegroundColor DarkGray
        }
    }
    else {
        Write-Host "未找到 opencode.db.bak,跳过。" -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host "=== 完成 ===" -ForegroundColor Cyan
