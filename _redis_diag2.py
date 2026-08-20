# -*- coding: utf-8 -*-
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.services import ssh_helper

HOST = "11.0.1.134"; USER = "root"; PWD = "123456"

def run(client, title, cmd):
    print("\n########## " + title + " ##########")
    try:
        stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
        print(stdout.read().decode('utf-8', errors='replace'))
        e = stderr.read().decode('utf-8', errors='replace')
        if e.strip(): print("[stderr]", e)
    except Exception as ex:
        print("[err]", ex)

client = None
try:
    client = ssh_helper.connect_ssh(HOST, 22, USER, password=PWD)
    # 1. systemd unit 文件
    run(client, "redis systemd unit", 'systemctl cat redis 2>/dev/null; echo ---; cat /usr/lib/systemd/system/redis.service 2>/dev/null; echo ---done---')
    # 2. 进程真实命令行 + 工作目录 + /proc dir
    run(client, "redis-server 完整 cmdline", 'pid=$(pgrep -x redis-server|head -1); echo pid=$pid; tr "\0" " " < /proc/$pid/cmdline; echo; echo -n "cwd="; readlink /proc/$pid/cwd; echo ---done---')
    # 3. 重启后 CONFIG GET dir 是否仍 /data/redis1 + info persistence
    run(client, "redis CONFIG GET dir + SAVE 状态", 'redis-cli -p 16379 -a redis123 CONFIG GET dir 2>/dev/null; redis-cli -p 16379 -a redis123 CONFIG GET dbfilename 2>/dev/null; redis-cli -p 16379 -a redis123 INFO persistence 2>/dev/null | grep -E "rdb_|aof_"; echo ---done---')
    # 4. /var/lib/redis dump.rdb 详情 + ls data/redis1
    run(client, "dump.rdb 与两个目录", 'ls -la /var/lib/redis/*.rdb 2>/dev/null; ls -la /data/redis1/ 2>/dev/null; echo ---done---')
finally:
    if client:
        try: client.close()
        except Exception: pass
print("\n===== DONE =====")
