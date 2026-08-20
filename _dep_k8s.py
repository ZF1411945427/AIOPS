# -*- coding: utf-8 -*-
"""k8s_offline_deploy_service.py 结构分析: 分区 + 顶层def + 跨函数依赖。"""
import re

PATH = "app/services/k8s_offline_deploy_service.py"
lines = open(PATH, encoding="utf-8").readlines()
total = len(lines)
print("总行数:", total)

sec_starts = []
for i, ln in enumerate(lines):
    if re.match(r"^\s*# [─\-─]+\s*.*$", ln) or re.match(r"^\s*# ─+", ln):
        sec_starts.append((i, ln.rstrip()))
print("\n=== 分区注释(共 %d) ===" % len(sec_starts))
for i, (line, raw) in enumerate(sec_starts):
    end = sec_starts[i + 1][0] if i + 1 < len(sec_starts) else total
    print("L%d-%d %s" % (line + 1, end, raw))

defs = []
for i, ln in enumerate(lines):
    m = re.match(r"^(def|class) (\w+)", ln)
    if m:
        defs.append((i + 1, m.group(1), m.group(2)))
print("\n=== 顶层 def/class 共 %d 个 ===" % len(defs))
for ln, kind, name in defs:
    print("%5d  %s %s" % (ln, "class" if kind == "class" else "def ", name))

# 跨函数依赖
fn_names = [n for _, k, n in defs]
print("\n=== 每函数引用本文件函数 ===")
for i, (ln, kind, name) in enumerate(defs):
    body_end = defs[i + 1][0] if i + 1 < len(defs) else total
    body = "\n".join(lines[ln - 1:body_end - 1])
    refs = []
    for other_ln, other_kind, other_name in defs:
        if other_name == name:
            continue
        if re.search(r"\b" + re.escape(other_name) + r"\s*\(", body):
            refs.append(other_name)
    if refs:
        print("%-38s -> %s" % (name, ", ".join(refs)))