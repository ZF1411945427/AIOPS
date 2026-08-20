# -*- coding: utf-8 -*-
"""列出 component_catalog_service 被外部引用的全部符号(门面 re-export 必须全覆盖)。"""
import re, glob

TARGET = "app/services/component_catalog_service.py"
# 本文件所有顶层符号
src = open(TARGET, encoding="utf-8").read()
own_syms = set(re.findall(r"^def (\w+)", src, re.M)) | set(re.findall(r"^class (\w+)", src, re.M))
own_names = set(re.findall(r"^_?[A-Za-z]\w*\s*=", src, re.M))
own_names = {n.split("=")[0].strip() for n in own_names if n.split("=")[0].strip().isidentifier()}
# 从文件引用:
# 1) from app.services.component_catalog_service import X
# 2) component_catalog_service.X 或 ccs.X
refs = set()
for f in glob.glob("app/**/*.py", recursive=True):
    if f.replace("\\", "/") == TARGET:
        continue
    text = open(f, encoding="utf-8", errors="ignore").read()
    for m in re.finditer(r"from app\.services\.component_catalog_service import ([^\n]+)", text):
        for part in m.group(1).split(","):
            refs.add(part.strip().split(" as ")[0].strip())
    for m in re.finditer(r"\b(?:component_catalog_service|ccs)\.(\w+)", text):
        refs.add(m.group(1))

print("=== 外部引用的符号(需 re-export) ===")
for s in sorted(refs):
    mark = "✓ 在本文件" if s in own_syms else ("常量?" if s in own_names else "✗ 缺失!")
    print("  %-38s %s" % (s, mark))
print("\n外部引用总数:", len(refs))