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
one("redis log 实际文件(file /var/log/redis) + grep err", 'cat /var/log/redis/redis.log 2>/dev/null | tail -50; echo ---; ls -la /var/log/redis/ 2>/dev/null; echo done')
one("SELinux 状态 + enforce", 'getenforce 2>/dev/null; sestatus 2>/dev/null | head -5; echo done')
one("redis SAVE 触发并立刻抓 server 日志", 'redis-cli -p 16379 -a redis123 SAVE; sleep 1; journalctl -u redis --no-pager -n 15 2>/dev/null | tail -15; echo done')
one("AVC SELinux 拒绝审计", 'grep -i "avc.*denied.*redis" /var/log/audit/audit.log 2>/dev/null | tail -10; echo done')
print("\n#### ALL DONE ####")
