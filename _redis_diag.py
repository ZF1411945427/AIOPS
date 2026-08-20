# -*- coding: utf-8 -*-
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.services import ssh_helper

HOST = "11.0.1.134"
USER = "root"
PWD = "123456"
PORT = 22

cmds = [
    ("[1] dump.rdb 实际落盘位置", 'find / -name "dump.rdb" 2>/dev/null; echo "---done---"'),
    ("[2] 所有 redis 进程", 'ps -ef | grep -i redis | grep -v grep; echo "---done---"'),
    ("[3] redis 进程 cmdline + cwd", '''
for pid in $(pgrep -x redis-server 2>/dev/null); do
  echo "== PID $pid =="
  tr '\0' ' ' < /proc/$pid/cmdline; echo
  echo -n "cwd: "; ls -l /proc/$pid/cwd 2>/dev/null | awk '{print $NF}'
done
echo "---done---"
'''),
    ("[4] /var/lib/redis 与 /data 目录", 'ls -la /var/lib/redis/ 2>/dev/null; echo "---"; ls -la /data/ 2>/dev/null; echo "---done---"'),
    ("[5] /etc/redis/redis.conf 关键行", 'grep -nE "^[[:space:]]*(dir|port|appendonly|save|requirepass|daemonize|pidfile|logfile)" /etc/redis/redis.conf 2>/dev/null; echo "---done---"'),
]

client = None
try:
    client = ssh_helper.connect_ssh(HOST, PORT, USER, password=PWD)
    for title, cmd in cmds:
        print("\n########## " + title + " ##########")
        stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
        out = stdout.read().decode('utf-8', errors='replace')
        err = stderr.read().decode('utf-8', errors='replace')
        print(out)
        if err.strip():
            print("[stderr]", err)
finally:
    if client:
        try:
            client.close()
        except Exception:
            pass
print("\n===== DONE =====")
