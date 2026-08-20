# -*- coding: utf-8 -*-
"""分析 component_catalog_service.py 的跨函数调用依赖, 决定安全的分组边界。"""
import re

PATH = "app/services/component_catalog_service.py"
lines = open(PATH, encoding="utf-8").readlines()

# 找域注释块(精确匹配该项目风格: # ───── 或 # ─── )
sec_starts = []
for i, ln in enumerate(lines):
    if re.match(r"^\s*# ─+ .*$", ln) or re.match(r"^\s*# ─+$", ln):
        sec_starts.append((i, ln.rstrip()))

print("=== 分区注释(共 %d) ===" % len(sec_starts))
for i, (line, raw) in enumerate(sec_starts):
    end = sec_starts[i + 1][0] if i + 1 < len(sec_starts) else len(lines)
    print("L%d-%d %s" % (line + 1, end, raw))

# 找所有顶层 def
defs = []
for i, ln in enumerate(lines):
    m = re.match(r"^def (\w+)", ln)
    if m:
        defs.append((i + 1, m.group(1)))
print("\n=== 顶层 def 共 %d 个 ===" % len(defs))

# 对每个函数, 统计它引用哪些本文件其他函数(文本级近似)
fn_names = [n for _, n in defs]
print("\n=== 每个函数内部引用的本文件函数 ===")
for i, (ln, name) in enumerate(defs):
    # 函数体范围: 从 def 行到下一个 def/分区
    body_end = defs[i + 1][0] if i + 1 < len(defs) else len(lines)
    body = "\n".join(lines[ln - 1:body_end - 1])
    refs = []
    for other_ln, other_name in defs:
        if other_name == name:
            continue
        # 用正则找 other_name( 的调用
        if re.search(r"\b" + re.escape(other_name) + r"\s*\(", body):
            refs.append(other_name)
    if refs:
        print("%-42s -> %s" % (name, ", ".join(refs)))