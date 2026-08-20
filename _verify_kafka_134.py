# -*- coding: utf-8 -*-
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.services import ssh_helper

HOST = "11.0.1.134"
USER = "root"
PWD = "123456"
PORT = 22

KAFKA_HOME = "/data/kafka"

cmds = [
    ("[1] Java 版本", 'java -version 2>&1; echo "---done---"'),
    ("[2] Kafka 目录结构", f'ls -la {KAFKA_HOME}/; echo "---"; ls -la {KAFKA_HOME}/bin/kafka-server-start.sh 2>/dev/null; echo "---done---"'),
    ("[3] Kafka 进程", 'ps aux | grep -i kafka | grep -v grep; echo "---done---"'),
    ("[4] 端口 9092 监听状态", 'ss -ltn 2>/dev/null | grep -E "9092|9093"; echo "---done---"'),
    ("[5] Cluster ID", 'cat /data/kafka-cluster.id 2>/dev/null; echo "---done---"'),
    ("[6] KRaft meta.properties", f'cat {KAFKA_HOME}/data/meta.properties 2>/dev/null; echo "---done---"'),
    ("[7] server.properties 关键配置",
     f'grep -nE "^(listeners|advertised|broker\\.id|log\\.dirs|default\\.replication|controller|process\\.roles|node\\.id)" '
     f'{KAFKA_HOME}/config/kraft/server.properties {KAFKA_HOME}/config/server.properties 2>/dev/null; echo "---done---"'),
    ("[8] 最新 server.log (末 50 行)", f'tail -50 {KAFKA_HOME}/logs/server.log 2>/dev/null; echo "---done---"'),
    ("[9] 数据目录大小", f'du -sh {KAFKA_HOME}/data/ 2>/dev/null; echo "---"; df -h {KAFKA_HOME} 2>/dev/null; echo "---done---"'),
    ("[10] SELinux 安全上下文", f'ls -Z {KAFKA_HOME}/ 2>/dev/null | head -5; echo "---"; getenforce 2>/dev/null; echo "---done---"'),
    ("[11] 防火墙 9092 端口", 'firewall-cmd --list-ports 2>/dev/null; echo "---"; firewall-cmd --list-services 2>/dev/null; echo "---done---"'),
    ("[12] 系统资源 (内存/磁盘)", 'free -h 2>/dev/null; echo "---"; df -h / 2>/dev/null; echo "---done---"'),
    ("[13] 自产自消验证 (创建 topic → 发送 → 消费)", f'''
TOPIC=verify-$(date +%s)
{KAFKA_HOME}/bin/kafka-topics.sh --create --topic $TOPIC --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1 2>&1
echo "HELLO_KAFKA_$(date +%Y%m%d%H%M%S)" | {KAFKA_HOME}/bin/kafka-console-producer.sh --topic $TOPIC --bootstrap-server localhost:9092 2>&1
RESULT=$({KAFKA_HOME}/bin/kafka-console-consumer.sh --topic $TOPIC --bootstrap-server localhost:9092 --from-beginning --max-messages 1 --timeout-ms 5000 2>&1)
echo "CONSUMED: $RESULT"
{KAFKA_HOME}/bin/kafka-topics.sh --delete --topic $TOPIC --bootstrap-server localhost:9092 2>&1
echo "---done---"
'''),
    ("[14] Kafka 版本", f'cat {KAFKA_HOME}/libs/kafka-*jar 2>/dev/null | head -1; ls {KAFKA_HOME}/libs/kafka_*.jar 2>/dev/null; echo "---done---"'),
]

client = None
try:
    client = ssh_helper.connect_ssh(HOST, PORT, USER, password=PWD)
    for title, cmd in cmds:
        print(f"\n{'='*60}")
        print(f"########## {title} ##########")
        print(f"{'='*60}")
        stdin, stdout, stderr = client.exec_command(cmd, timeout=120)
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
print("\n" + "="*60)
print("===== Kafka 部署验证完成 =====")