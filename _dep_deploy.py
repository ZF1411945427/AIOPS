# -*- coding: utf-8 -*-
"""分析 deploy_service.py 的分区注释 + 跨函数依赖, 制定分组边界。"""
import re

PATH = "app/services/deploy_service.py"
lines = open(PATH, encoding="utf-8").readlines()

sec_starts = []
for i, ln in enumerate(lines):
    if re.match(r"^\s*# ─+ .*$", ln):
        sec_starts.append((i, ln.rstrip()))

print("=== 分区注释(共 %d) ===" % len(sec_starts))
for i, (line, raw) in enumerate(sec_starts):
    end = sec_starts[i + 1][0] if i + 1 < len(sec_starts) else len(lines)
    print("L%d-%d %s" % (line + 1, end, raw))

defs = []
for i, ln in enumerate(lines):
    m = re.match(r"^def (\w+)", ln)
    if m:
        defs.append((i + 1, m.group(1)))
print("\n=== 顶层 def 共 %d 个 ===" % len(defs))

fn_names = [n for _, n in defs]
print("\n=== 每个函数内部引用的本文件函数 ===")
for i, (ln, name) in enumerate(defs):
    body_end = defs[i + 1][0] if i + 1 < len(defs) else len(lines)
    body = "\n".join(lines[ln - 1:body_end - 1])
    refs = []
    for other_ln, other_name in defs:
        if other_name == name:
            continue
        if re.search(r"\b" + re.escape(other_name) + r"\s*\(", body):
            refs.append(other_name)
    if refs:
        print("%-40s -> %s" % (name, ", ".join(refs)))