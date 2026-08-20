# -*- coding: utf-8 -*-
"""deploy_service 拆分准备: 模块级常量行号 + 外部引用清单。"""
import re, glob

PATH = "app/services/deploy_service.py"
lines = open(PATH, encoding="utf-8").readlines()

print("=== 模块级常量(无缩进的 NAME =) ===")
for i, ln in enumerate(lines):
    m = re.match(r"^([A-Z_][A-Z0-9_]*)\s*=", ln)
    if m:
        print("%5d  %s" % (i + 1, m.group(1)))

print("\n=== 外部引用(from app.services.deploy_service import / deploy_service.X) ===")
src_own = "\n".join(lines)
own_names = set(re.findall(r"^def (\w+)", src_own, re.M)) | set(re.findall(r"^([A-Z_][A-Z0-9_]*)\s*=", src_own, re.M))
refs = set()
for f in glob.glob("app/**/*.py", recursive=True):
    if "deploy_service.py" in f.replace("\\", "/"):
        continue
    text = open(f, encoding="utf-8", errors="ignore").read()
    for m in re.finditer(r"from app\.services\.deploy_service import ([^\n]+)", text):
        for part in m.group(1).split(","):
            refs.add(part.strip().split(" as ")[0].strip())
    for m in re.finditer(r"\bdeploy_service\.(\w+)", text):
        refs.add(m.group(1))
for s in sorted(refs):
    if not s or s == "(":
        continue
    mark = "OK" if s in own_names else "缺失?"
    print("  %-38s %s" % (s, mark))
print("外部引用数:", len([s for s in refs if s and s != '(']))