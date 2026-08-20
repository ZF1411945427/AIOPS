#!/usr/bin/env python
"""以 PG 模式后台启动后端: 注入 AIOPS_DB_URL 后拉起 run.py(新窗口)。"""
import os
import sys
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env = dict(os.environ)
env["AIOPS_DB_URL"] = "postgresql://aiops:aiops-secret@127.0.0.1:5432/aiops"
env.setdefault("APP_ENV", "dev")

# 新窗口启动, 便于单独观察后端日志
subprocess.Popen(
    [sys.executable, "run.py"],
    cwd=ROOT,
    env=env,
    creationflags=subprocess.CREATE_NEW_CONSOLE,
)
print("backend started with AIOPS_DB_URL (PG)")