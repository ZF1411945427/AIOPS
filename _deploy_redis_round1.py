# -*- coding: utf-8 -*-
"""第1轮/A组 Redis 部署: 11.0.1.134"""
import sys, os, io, time, base64
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paramiko

HOST = "11.0.1.134"
USER = "root"
PWD = "123456"
PORT = 16379
PW = "redis123"
DATA_DIR = "/data/redis1"

def run_ssh(ssh, cmd, timeout=60):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    return exit_code, out, err

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    log(f"Connecting to {HOST} ...")
    ssh.connect(HOST, 22, USER, password=PWD, timeout=15)
    log("Connected.")

    # 第1步: 安装 Redis
    log("Step 1: Install Redis ...")
    rc, out, err = run_ssh(ssh, "rpm -q redis 2>/dev/null || yum install -y redis 2>&1", timeout=120)
    if rc != 0:
        log(f"WARN: yum install exit code={rc}, err={err[:300]}")
    else:
        log("Redis installed.")

    # 第2步: 停旧服务 + 创建数据目录
    log("Step 2: Stop old service & create data dir ...")
    script = f"""
systemctl stop redis-server redis 2>/dev/null || true
pkill -9 redis-server 2>/dev/null || true
sleep 1
mkdir -p '{DATA_DIR}' && chown redis:redis '{DATA_DIR}' 2>/dev/null || true
"""
    rc, out, err = run_ssh(ssh, script, timeout=30)
    log(f"  dir setup: {out[:200] if out else 'ok'}")

    # 第3步: SELinux 修复
    log("Step 3: SELinux fix for data dir ...")
    cmd = (
        f"if command -v semanage >/dev/null 2>&1 && [ \"$(getenforce 2>/dev/null)\" = \"Enforcing\" ]; then "
        f"semanage fcontext -a -t redis_var_lib_t '{DATA_DIR}(/.*)?' 2>/dev/null || true; "
        f"restorecon -Rv '{DATA_DIR}' >/dev/null 2>&1 || true; "
        f"echo SELINUX_FIXED; "
        f"else echo SELINUX_SKIP; fi"
    )
    rc, out, err = run_ssh(ssh, cmd, timeout=30)
    log(f"  SELinux: {out}")

    # 第4步: 修改配置 - 端口 / 密码 / 数据目录 / bind / protected-mode
    log("Step 4: Configure Redis ...")
    cfg = "/etc/redis/redis.conf"
    pw_b64 = base64.urlsafe_b64encode(PW.encode("utf-8")).decode("ascii")
    script = f"""
CFG={cfg}
[ -f $CFG ] && cp $CFG $CFG.bak.$(date +%s) || true
sed -i -E '/^[[:space:]]*#?[[:space:]]*port[[:space:]]/d' $CFG || true
echo 'port {PORT}' >> $CFG
sed -i -E '/^[[:space:]]*#?[[:space:]]*bind[[:space:]]/d' $CFG || true
echo 'bind 0.0.0.0' >> $CFG
sed -i -E '/^[[:space:]]*#?[[:space:]]*protected-mode[[:space:]]/d' $CFG || true
echo 'protected-mode no' >> $CFG
sed -i -E '/^[[:space:]]*#?[[:space:]]*requirepass[[:space:]]/d' $CFG || true
umask 077; echo '{pw_b64}' | base64 -d > /tmp/.aiops_redis_pw 2>/dev/null || true
printf 'requirepass ' >> $CFG; cat /tmp/.aiops_redis_pw >> $CFG; echo >> $CFG
sed -i -E 's/^#?\\s*maxmemory\\s+.*/maxmemory 512MB/' $CFG
grep -q '^maxmemory ' $CFG || echo 'maxmemory 512MB' >> $CFG
sed -i -E 's|^#?\\s*dir\\s+.*|dir {DATA_DIR}|' $CFG
grep -q '^dir ' $CFG || echo 'dir {DATA_DIR}' >> $CFG
chown redis:redis $CFG; chmod 640 $CFG; chmod 750 /etc/redis 2>/dev/null || true
echo CONFIG_DONE
"""
    rc, out, err = run_ssh(ssh, script, timeout=30)
    log(f"  config: {out[:200]}")

    # 第5步: 启动
    log("Step 5: Start Redis ...")
    cmd = "systemctl daemon-reload 2>/dev/null; systemctl enable --now redis 2>/dev/null; systemctl restart redis 2>/dev/null || service redis restart 2>/dev/null; echo START_DONE"
    rc, out, err = run_ssh(ssh, cmd, timeout=30)
    log(f"  start: {out[:200]}")

    # 第6步: 验证
    log("Step 6: Verify ...")
    cmd = f"""
_u=0; for _i in $(seq 1 10); do
redis-cli -p {PORT} -a '{PW}' ping 2>/dev/null | grep -q PONG && {{ _u=1; break; }}; sleep 1; done
echo "__UP=$_u"
"""
    rc, out, err = run_ssh(ssh, cmd, timeout=30)
    log(f"  verify: {out}")

    # 第7步: 详细验证
    log("Step 7: Detailed verification ...")
    cmds = [
        ("redis-cli PING", f"redis-cli -p {PORT} -a '{PW}' ping 2>&1"),
        ("redis-cli INFO server", f"redis-cli -p {PORT} -a '{PW}' INFO server 2>&1 | head -10"),
        ("redis-cli CONFIG GET dir", f"redis-cli -p {PORT} -a '{PW}' CONFIG GET dir 2>&1"),
        ("redis-cli CONFIG GET port", f"redis-cli -p {PORT} -a '{PW}' CONFIG GET port 2>&1"),
        ("SAVE test", f"redis-cli -p {PORT} -a '{PW}' SAVE 2>&1"),
        ("数据目录文件", f"ls -la {DATA_DIR}/ 2>&1"),
        ("端口监听", f"ss -tlnp | grep {PORT} 2>&1"),
    ]
    for title, c in cmds:
        rc, out, err = run_ssh(ssh, c, timeout=15)
        print(f"  [{title}] {out[:200]}")
        if err:
            print(f"  [stderr] {err[:200]}")

    # 清理临时密码文件
    run_ssh(ssh, "rm -f /tmp/.aiops_redis_pw 2>/dev/null || true", timeout=5)

    ssh.close()
    log("=== REDIS 第1轮/A组 部署完成 ===")

if __name__ == "__main__":
    main()