# -*- coding: utf-8 -*-
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.services import ssh_helper

HOST="11.0.1.134"; USER="root"; PWD="123456"

def one(title, cmd):
    print("\n########## "+title+" ##########")
    client=None
    try:
        client=ssh_helper.connect_ssh(HOST,22,USER,password=PWD,timeout=10)
        for _ in range(3):
            stdin,stdout,stderr=client.exec_command(cmd,timeout=40)
            out=stdout.read().decode('utf-8',errors='replace')
            if out: print(out); break
        e=stderr.read().decode('utf-8',errors='replace')
        if e.strip(): print("[stderr]",e[:2000])
    except Exception as ex:
        print("[err]",type(ex).__name__,ex)
    finally:
        if client:
            try: client.close()
            except Exception: pass

one("redis 进程 cmdline+cwd+dir", 'pid=$(pgrep -x redis-server|head -1); echo pid=$pid; tr "\0" " " < /proc/$pid/cmdline; echo; echo -n "cwd="; readlink /proc/$pid/cwd 2>/dev/null; echo')
one("CONFIG GET dir/dbfilename", 'redis-cli -p 16379 -a redis123 CONFIG GET dir 2>/dev/null; redis-cli -p 16379 -a redis123 CONFIG GET dbfilename 2>/dev/null; echo done')
one("两个目录 + dump 时间", 'ls -la --time-style=full-iso /var/lib/redis/*.rdb 2>/dev/null; echo ---; ls -la --time-style=full-iso /data/redis1/ 2>/dev/null; echo done')
one("SAVE 后看落盘", 'redis-cli -p 16379 -a redis123 SAVE 2>&1; sleep 2; ls -la /data/redis1/ 2>/dev/null; ls -la /var/lib/redis/*.rdb 2>/dev/null; echo done')
print("\n===== ALL DONE =====")
