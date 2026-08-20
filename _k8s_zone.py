# -*- coding: utf-8 -*-
"""k8s_offline_deploy_service.py 拆分: 按功能区规划 + 外部引用清单 + 状态归属。"""
import re, glob

PATH = "app/services/k8s_offline_deploy_service.py"
lines = open(PATH, encoding="utf-8").readlines()

def block_lines(start, end):
    """start,end 1-based 包含端"""
    out = []
    for i in range(start - 1, end):
        out.append(lines[i])
    # 去尾部连续空行
    while out and not out[-1].strip():
        out.pop()
    return out

# 功能区(1-based)
zones = {
    "header+state":      (1, 133),
    "base_tools":        (134, 290),
    "crud":              (291, 464),
    "orchestration":     (465, 584),
    "stop_guard":        (585, 1147),
    "docker_runtime":    (1148, 1578),
    "ai_precheck":       (1579, 1860),
    "exec_phases":       (1861, 2855),
    "persist":           (2856, 3081),
}
total = 0
for name, (s, e) in zones.items():
    n = len(block_lines(s, e))
    total += n
    print("%-16s L%-4d-%-4d  %4d 行" % (name, s, e, n))
print("合计:", total)

print("\n=== 外部引用 ===")
own = set(re.findall(r"^def (\w+)", "".join(lines), re.M))
refs = set()
for f in glob.glob("app/**/*.py", recursive=True):
    if "k8s_offline_deploy_service.py" in f.replace("\\", "/"):
        continue
    text = open(f, encoding="utf-8", errors="ignore").read()
    for m in re.finditer(r"from app\.services\.k8s_offline_deploy_service import ([^\n]+)", text):
        for part in m.group(1).split(","):
            refs.add(part.strip().split(" as ")[0].strip())
    for m in re.finditer(r"\b(?:k8s_offline_deploy_service|kods)\.(\w+)", text):
        refs.add(m.group(1))
for s in sorted(refs):
    if not s or s == "(":
        continue
    print("  %-36s %s" % (s, "OK" if s in own else "缺失?"))