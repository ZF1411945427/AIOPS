# -*- coding: utf-8 -*-
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.services import ssh_helper
HOST="11.0.1.134"; USER="root"; PWD="123456"
def one(title, cmd):
    print("\n##### "+title+" #####")
    client=None
    try:
        client=ssh_helper.connect_ssh(HOST,22,USER,password=PWD,timeout=10)
        for _ in range(3):
            stdin,stdout,stderr=client.exec_command(cmd,timeout=40)
            out=stdout.read().decode('utf-8',errors='replace')
            if out.strip(): print(out); break
        e=stderr.read().decode('utf-8',errors='replace')
        if e.strip(): print("[stderr]",e[:1500])
    except Exception as ex:
        print("[err]",type(ex).__name__,ex)
    finally:
        if client:
            try: client.close()
            except Exception: pass
one("redis 日志尾部", 'journalctl -u redis --no-pager -n 40 2>/dev/null; echo ---done---')
one("/data/redis1 可写测试(redis用户)", 'su redis -s /bin/bash -c "touch /data/redis1/.write_test 2>&1 && echo WRITE_OK && ls -la /data/redis1/"; rm -f /data/redis1/.write_test 2>/dev/null; echo done')
one("/data 文件系统与权限", 'df -h /data; mount | grep -E " /data| / " ; ls -ld /data /data/redis1; echo done')
one("redis CONFIG GET maxmemory + 实际错误日志文件", 'redis-cli -p 16379 -a redis123 CONFIG GET maxmemory 2>/dev/null; grep -rn "dir " /etc/redis/redis.conf; echo done')
print("\n#### ALL DONE ####")
