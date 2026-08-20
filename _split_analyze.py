# -*- coding: utf-8 -*-
"""分析 mcp_tools.py 的域注释块边界与每个块内的函数, 输出分组方案预览。"""
import re

PATH = "app/services/mcp_tools.py"
lines = open(PATH, encoding="utf-8").readlines()
total = len(lines)
print("总行数:", total)

# 找域注释行
sections = []  # (start_line_idx, title)
for i, ln in enumerate(lines):
    m = re.match(r"^# ───\s*(.*?)\s*─*$", ln.rstrip())
    if m:
        sections.append((i, m.group(1).strip(), ln.rstrip()))

# 找所有顶层 def / 装饰器
defs = []
for i, ln in enumerate(lines):
    m = re.match(r"^def (\w+)", ln)
    if m:
        defs.append((i, m.group(1)))

print("\n=== 域注释块(共 %d) ===" % len(sections))
for idx, (line, title, raw) in enumerate(sections):
    end = sections[idx + 1][0] if idx + 1 < len(sections) else total
    # 块内定义的函数
    fns = [name for (ln, name) in defs if line <= ln < end]
    print("L%d-%d [%s] 函数(%d): %s" % (line + 1, end, title, len(fns), ", ".join(fns[:60])))

print("\n=== 顶层 def 总分布 ===")
print("def 数量:", len(defs))