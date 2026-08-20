# -*- coding: utf-8 -*-
"""列出 deploy_service.py 全部顶层 def + 行号, 并判断 AI 簇依赖方向。"""
import re

lines = open("app/services/deploy_service.py", encoding="utf-8").readlines()

defs = []
for i, ln in enumerate(lines):
    m = re.match(r"^(def|class) (\w+)", ln)
    if m:
        defs.append((i + 1, m.group(2)))

print("=== 全部顶层符号 (行号, 名称) ===")
for ln, name in defs:
    print("%5d  %s" % (ln, name))
print("\n共 %d 个" % len(defs))