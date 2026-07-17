"""实时诊断 Tool 标准化 API — Snapshot/Focused/Flexible 三层工具体系.

对标 GOPS 2026 秦晓辉演讲《借力 AI RCA》Layer3 实时诊断层设计：
- Snapshot 快照工具：全局状态概览（os.overview, mysql.overview, redis.overview）
- Focused 定向工具：针对性深度诊断（mysql.lock_contention, redis.slowlog）
- Flexible 灵活受控工具：受限 shell（AST 白名单）、SQL 查询
"""
import re
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models import Asset
from app.services.ssh_helper import get_ssh_client

router = APIRouter(prefix="/api/diagnostic-tools", tags=["diagnostic-tools"])


DIAGNOSTIC_TOOLS = [
    # ── Snapshot 快照工具 ──
    {
        "id": "os.overview",
        "name": "OS 系统概览",
        "category": "snapshot",
        "description": "快速获取操作系统全局状态：CPU、内存、磁盘、负载、进程数、网络连接数",
        "command": "echo '=== CPU ===' && top -bn1 | head -5 && echo '=== MEM ===' && free -h && echo '=== DISK ===' && df -h / && echo '=== LOAD ===' && uptime && echo '=== PROCS ===' && ps aux | wc -l && echo '=== NET ===' && ss -s",
        "risk_level": "read_only",
        "timeout": 15,
        "target_type": "host",
    },
    {
        "id": "mysql.overview",
        "name": "MySQL 概览",
        "category": "snapshot",
        "description": "MySQL 全局状态快照：连接数、线程数、慢查询数、QPS、缓冲池命中率",
        "command": "mysql -e \"SHOW GLOBAL STATUS WHERE Variable_name IN ('Threads_connected','Threads_running','Slow_queries','Queries','Uptime','Innodb_buffer_pool_read_requests','Innodb_buffer_pool_reads');\" 2>/dev/null || echo 'MySQL not accessible'",
        "risk_level": "read_only",
        "timeout": 15,
        "target_type": "host",
    },
    {
        "id": "redis.overview",
        "name": "Redis 概览",
        "category": "snapshot",
        "description": "Redis 全局状态快照：内存、连接、QPS、Key 数、命中率",
        "command": "redis-cli info memory clients stats 2>/dev/null | grep -E 'used_memory_human|connected_clients|total_commands_processed|keyspace_hits|keyspace_misses|expired_keys|evicted_keys' || echo 'Redis not accessible'",
        "risk_level": "read_only",
        "timeout": 15,
        "target_type": "host",
    },
    {
        "id": "nginx.overview",
        "name": "Nginx 概览",
        "category": "snapshot",
        "description": "Nginx 连接状态：活跃连接、请求数、读写等待数",
        "command": "nginx -T 2>/dev/null | grep -c 'server_name' && echo '---' && (ss -tnp | grep nginx | wc -l) || echo 'Nginx not found'",
        "risk_level": "read_only",
        "timeout": 10,
        "target_type": "host",
    },
    {
        "id": "docker.overview",
        "name": "Docker 容器概览",
        "category": "snapshot",
        "description": "Docker 容器状态：运行/停止/暂停数、资源使用",
        "command": "docker ps -a --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}' 2>/dev/null && echo '---' && docker stats --no-stream --format 'table {{.Name}}\\t{{.CPUPerc}}\\t{{.MemUsage}}' 2>/dev/null || echo 'Docker not available'",
        "risk_level": "read_only",
        "timeout": 15,
        "target_type": "host",
    },
    {
        "id": "network.overview",
        "name": "网络连接概览",
        "category": "snapshot",
        "description": "网络连接状态：TCP 连接数、监听端口、ESTABLISHED/TIME_WAIT 统计",
        "command": "echo '=== LISTENING ===' && ss -tlnp && echo '=== ESTABLISHED ===' && ss -tnp state established | wc -l && echo '=== TIME_WAIT ===' && ss -tnp state time-wait | wc -l && echo '=== CONNECTIONS ===' && ss -s",
        "risk_level": "read_only",
        "timeout": 10,
        "target_type": "host",
    },
    # ── Focused 定向工具 ──
    {
        "id": "mysql.lock_contention",
        "name": "MySQL 锁等待分析",
        "category": "focused",
        "description": "诊断 MySQL 行锁等待：阻塞会话、源头事务、冲突 SQL",
        "command": "mysql -e \"SELECT r.trx_id AS waiting_trx, r.trx_mysql_thread_id AS waiting_thread, r.trx_query AS waiting_query, b.trx_id AS blocking_trx, b.trx_mysql_thread_id AS blocking_thread, b.trx_query AS blocking_query FROM information_schema.innodb_lock_waits w INNER JOIN information_schema.innodb_trx b ON b.trx_id = w.blocking_trx_id INNER JOIN information_schema.innodb_trx r ON r.trx_id = w.requesting_trx_id;\" 2>/dev/null || echo 'No lock contention or MySQL not accessible'",
        "risk_level": "read_only",
        "timeout": 15,
        "target_type": "host",
    },
    {
        "id": "mysql.slowlog",
        "name": "MySQL 慢查询",
        "category": "focused",
        "description": "查看最近 10 条慢查询日志",
        "command": "mysqldumpslow -s t -t 10 /var/log/mysql/mysql-slow.log 2>/dev/null || mysql -e \"SELECT * FROM mysql.slow_log ORDER BY start_time DESC LIMIT 10;\" 2>/dev/null || echo 'Slow log not available'",
        "risk_level": "read_only",
        "timeout": 15,
        "target_type": "host",
    },
    {
        "id": "mysql.processlist",
        "name": "MySQL 进程列表",
        "category": "focused",
        "description": "查看 MySQL 当前所有连接和执行中的 SQL",
        "command": "mysql -e \"SHOW FULL PROCESSLIST;\" 2>/dev/null || echo 'MySQL not accessible'",
        "risk_level": "read_only",
        "timeout": 10,
        "target_type": "host",
    },
    {
        "id": "redis.slowlog",
        "name": "Redis 慢日志",
        "category": "focused",
        "description": "查看 Redis 最近 10 条慢命令",
        "command": "redis-cli slowlog get 10 2>/dev/null || echo 'Redis not accessible'",
        "risk_level": "read_only",
        "timeout": 10,
        "target_type": "host",
    },
    {
        "id": "redis.bigkey",
        "name": "Redis 大 Key 扫描",
        "category": "focused",
        "description": "扫描 Redis 中占用内存较大的 Key（采样模式）",
        "command": "redis-cli --bigkeys --sample 1000 2>/dev/null || echo 'Redis not accessible'",
        "risk_level": "read_only",
        "timeout": 30,
        "target_type": "host",
    },
    {
        "id": "disk.usage",
        "name": "磁盘大文件分析",
        "category": "focused",
        "description": "查找磁盘上最大的 20 个文件",
        "command": "find / -type f -size +100M -exec ls -lh {} \\; 2>/dev/null | sort -k5 -rh | head -20",
        "risk_level": "read_only",
        "timeout": 30,
        "target_type": "host",
    },
    {
        "id": "disk.inode",
        "name": "Inode 使用分析",
        "category": "focused",
        "description": "检查各分区 inode 使用率和最大目录",
        "command": "df -i && echo '---' && for d in /*; do echo \"$(find $d -xdev 2>/dev/null | wc -l) $d\"; done | sort -rn | head -10",
        "risk_level": "read_only",
        "timeout": 30,
        "target_type": "host",
    },
    {
        "id": "memory.top",
        "name": "内存 Top 进程",
        "category": "focused",
        "description": "内存占用最高的 10 个进程",
        "command": "ps aux --sort=-%mem | head -11",
        "risk_level": "read_only",
        "timeout": 10,
        "target_type": "host",
    },
    {
        "id": "cpu.top",
        "name": "CPU Top 进程",
        "category": "focused",
        "description": "CPU 占用最高的 10 个进程",
        "command": "ps aux --sort=-%cpu | head -11",
        "risk_level": "read_only",
        "timeout": 10,
        "target_type": "host",
    },
    {
        "id": "file.handle",
        "name": "文件句柄分析",
        "category": "focused",
        "description": "系统文件句柄使用情况和 Top 进程",
        "command": "cat /proc/sys/fs/file-nr && echo '---' && lsof -n 2>/dev/null | awk '{print $2}' | sort | uniq -c | sort -rn | head -10",
        "risk_level": "read_only",
        "timeout": 20,
        "target_type": "host",
    },
    {
        "id": "journal.errors",
        "name": "系统日志错误",
        "category": "focused",
        "description": "最近 50 条系统日志中的 ERROR/CRITICAL",
        "command": "journalctl -p err --since '1 hour ago' --no-pager | tail -50 2>/dev/null || dmesg | grep -iE 'error|critical|fail' | tail -50",
        "risk_level": "read_only",
        "timeout": 15,
        "target_type": "host",
    },
    {
        "id": "network.tcpdump",
        "name": "网络连接追踪",
        "category": "focused",
        "description": "当前活跃 TCP 连接的来源和目标统计",
        "command": "ss -tnp state established | awk '{print $5}' | cut -d: -f1 | sort | uniq -c | sort -rn | head -20",
        "risk_level": "read_only",
        "timeout": 10,
        "target_type": "host",
    },
    # ── Flexible 灵活受控工具 ──
    {
        "id": "flex.shell",
        "name": "自定义 Shell 命令",
        "category": "flexible",
        "description": "执行自定义只读 Shell 命令（AST 白名单校验，仅允许只读命令）",
        "command": None,
        "risk_level": "read_only",
        "timeout": 30,
        "target_type": "host",
        "custom": True,
    },
    {
        "id": "flex.mysql",
        "name": "自定义 SQL 查询",
        "category": "flexible",
        "description": "执行只读 SQL 查询（仅允许 SELECT/SHOW/DESC）",
        "command": None,
        "risk_level": "read_only",
        "timeout": 30,
        "target_type": "host",
        "custom": True,
    },
]

READ_ONLY_PREFIXES = {
    "ps", "df", "free", "top", "grep", "egrep", "fgrep", "which", "whereis",
    "echo", "date", "ls", "ll", "cat", "head", "tail", "wc", "uname", "whoami",
    "id", "env", "printenv", "hostname", "ip", "ifconfig", "uptime", "who",
    "last", "find", "ss", "netstat", "lsof", "stat", "file", "du", "lsblk",
    "journalctl", "dmesg", "rpm", "test", "pwd", "basename", "dirname",
    "realpath", "readlink", "md5sum", "sha256sum", "cksum", "cut", "tr",
    "sort", "uniq", "awk", "sed", "mysql", "redis-cli", "docker", "nginx",
    "mysqldumpslow", "find",
}

DANGEROUS_PATTERNS = [
    r"rm\s+-rf", r"mkfs", r"dd\s+if=", r"shutdown", r"reboot", r"halt",
    r"init\s+[06]", r":\(\):\{", r"fork\s+bomb", r">\s*/dev/sd",
    r"chmod\s+-R\s+777", r"chown\s+-R", r"iptables\s+-F", r"iptables\s+-X",
    r"curl.*\|.*sh", r"wget.*\|.*sh", r"eval\s", r">\s*/dev/null\s+2>&1\s*&",
    r"nohup", r"crontab", r"useradd", r"userdel", r"usermod", r"passwd",
    r"visudo", r"systemctl\s+(start|stop|restart|enable|disable)",
    r"service\s+\w+\s+(start|stop|restart)",
    r"kill\s+-9", r"killall", r"pkill",
    r"mount", r"umount", r"fdisk", r"parted",
    r"scp", r"rsync",
    r"mysql.*INSERT", r"mysql.*UPDATE", r"mysql.*DELETE", r"mysql.*DROP",
    r"mysql.*CREATE", r"mysql.*ALTER", r"mysql.*TRUNCATE", r"mysql.*GRANT",
    r"redis-cli.*flush", r"redis-cli.*del",
]


def validate_command(command: str) -> tuple:
    if not command or not command.strip():
        return False, "命令不能为空"
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return False, f"命令包含危险操作模式: {pattern}"
    parts = re.split(r'\|\||&&|;|\|', command)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        tokens = part.split()
        if not tokens:
            continue
        if tokens[0] == "sudo" and len(tokens) > 1:
            tokens = tokens[1:]
        first = tokens[0]
        if first not in READ_ONLY_PREFIXES:
            return False, f"命令 '{first}' 不在只读白名单中，已拦截"
    return True, "OK"


@router.get("/registry")
def get_tool_registry():
    categories = {"snapshot": [], "focused": [], "flexible": []}
    for t in DIAGNOSTIC_TOOLS:
        cat = t["category"]
        if cat in categories:
            categories[cat].append(t)
    return {
        "total": len(DIAGNOSTIC_TOOLS),
        "categories": categories,
        "summary": {
            "snapshot": len(categories["snapshot"]),
            "focused": len(categories["focused"]),
            "flexible": len(categories["flexible"]),
        },
    }


@router.get("/categories")
def get_categories():
    return {
        "categories": [
            {
                "key": "snapshot",
                "label": "Snapshot 快照工具",
                "description": "全局状态概览，快速初筛，无需参数",
                "icon": "View",
                "color": "#6366f1",
            },
            {
                "key": "focused",
                "label": "Focused 定向工具",
                "description": "针对性深度诊断，验证故障假设",
                "icon": "Aim",
                "color": "#f59e0b",
            },
            {
                "key": "flexible",
                "label": "Flexible 灵活受控工具",
                "description": "自定义命令/SQL，AST 白名单校验",
                "icon": "EditPen",
                "color": "#10b981",
            },
        ]
    }


class ExecuteToolBody(BaseModel):
    tool_id: str
    asset_id: int
    custom_command: Optional[str] = None


@router.post("/execute")
def execute_tool(body: ExecuteToolBody, db: Session = Depends(get_db)):
    tool = next((t for t in DIAGNOSTIC_TOOLS if t["id"] == body.tool_id), None)
    if not tool:
        raise HTTPException(404, f"诊断工具 '{body.tool_id}' 不存在")

    asset = db.query(Asset).filter(Asset.id == body.asset_id).first()
    if not asset:
        raise HTTPException(404, "目标资产不存在")

    command = tool.get("command")
    if tool.get("custom"):
        command = body.custom_command
        if not command:
            raise HTTPException(400, "自定义工具需要提供 custom_command 参数")
        valid, msg = validate_command(command)
        if not valid:
            raise HTTPException(403, f"命令安全校验失败: {msg}")

    if not command:
        raise HTTPException(400, "无法构造诊断命令")

    try:
        import json as _json
        cfg = _json.loads(asset.connection_config or "{}") if isinstance(asset.connection_config, str) else (asset.connection_config or {})
    except Exception:
        cfg = {}

    host = asset.ip or ""
    if not host:
        raise HTTPException(400, f"资产 {asset.name} 无 IP 地址")

    timeout = tool.get("timeout", 30)
    try:
        ssh = get_ssh_client()
        ssh.connect(
            host, port=cfg.get("ssh_port", 22),
            username=cfg.get("ssh_user", "root"),
            password=cfg.get("ssh_password", ""),
            timeout=15, banner_timeout=15,
        )
        _, stdout, stderr = ssh.exec_command(command, timeout=timeout)
        out = stdout.read().decode(errors="ignore").strip()
        err = stderr.read().decode(errors="ignore").strip()
        code = stdout.channel.recv_exit_status()
        ssh.close()
        result = "\n".join(s for s in [out, err] if s) or f"exit_code={code}"
        return {
            "tool_id": body.tool_id,
            "tool_name": tool["name"],
            "asset_name": asset.name,
            "asset_ip": host,
            "command": command,
            "output": result,
            "exit_code": code,
            "success": code == 0,
            "executed_at": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "tool_id": body.tool_id,
            "tool_name": tool["name"],
            "asset_name": asset.name,
            "asset_ip": host,
            "command": command,
            "output": f"执行失败: {e}",
            "exit_code": -1,
            "success": False,
            "executed_at": datetime.now().isoformat(),
        }


class ValidateBody(BaseModel):
    command: str


@router.post("/validate")
def validate_command_api(body: ValidateBody):
    valid, msg = validate_command(body.command)
    return {"valid": valid, "message": msg, "command": body.command}


from datetime import datetime
