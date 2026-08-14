import subprocess

# 通过 sc.exe 查询 VMware NAT Service 详细
p = subprocess.run(["sc.exe", "qc", "VMware NAT Service"], capture_output=True, text=True, encoding="gbk")
print("=== sc qc VMware NAT Service ===")
print(p.stdout)
print(p.stderr)

# 看 vmnetdhcp 服务路径
p2 = subprocess.run(["sc.exe", "qc", "VMnetDHCP"], capture_output=True, text=True, encoding="gbk")
print("\n=== sc qc VMnetDHCP ===")
print(p2.stdout)
print(p2.stderr)

# 看 vmci 等其他 VMware 服务
p3 = subprocess.run(["sc.exe", "query", "type=", "service"], capture_output=True, text=True, encoding="gbk")
# 过滤 vmware 相关的
import re
for line in p3.stdout.splitlines():
    if "VMWARE" in line.upper() or "VMCI" in line.upper() or "VMMOUSE" in line.upper() or "VMTools" in line.upper():
        print(line)