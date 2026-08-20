# -*- coding: utf-8 -*-
"""D1: 把 8 个 view 的裸 axios 迁移到统一 request(@/api/request)。
幂等: 已迁移的文件跳过。仅处理含 "import axios from 'axios'" 的文件。
"""
import io, os, re

P = "frontend/src/views"
TARGETS = [
    "ChaosScenarioView.vue", "ComponentStoreView.vue", "ConfigDriftView.vue",
    "ChaosReportView.vue", "ChaosExperimentView.vue", "InspectionView.vue",
    "ProvidersView.vue", "TenantManagementView.vue",
]

def read(path):
    with io.open(path, "r", encoding="utf-8-sig") as f:
        return f.read()

def write(path, text):
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)

AXIOS_IMPORT = re.compile(r"^import axios from ['\"]axios['\"]\s*$", re.M)

def migrate(path):
    text = read(path)
    if "import axios from 'axios'" not in text and "import axios from \"axios\"" not in text:
        return None  # 无裸 axios, 跳过(幂等)
    # 1. import 替换
    text = re.sub(r"import axios from ['\"]axios['\"]", "import request from '@/api/request'", text)
    # 2. 解构替换(需在 axios.->request. 之前, 因为含 axios. 字样)
    #    处理各种空白形式: { data } / {data} / { data: x } / {data:x}
    text = re.sub(r"const\s*\{\s*data\s*:\s*(\w+)\s*\}\s*=\s*await\s+axios\.", r"const \1 = await request.", text)
    text = re.sub(r"const\s*\{\s*data\s*\}\s*=\s*await\s+axios\.", "const data = await request.", text)
    # 3. 剩余 axios.[...] -> request.[...]
    text = re.sub(r"\baxios\.", "request.", text)
    write(path, text)
    return "migrated"

for f in TARGETS:
    path = os.path.join(P, f)
    try:
        r = migrate(path)
        if r:
            t = read(path)
            remain = len(re.findall(r"\baxios\.", t))
            imp = "import request from '@/api/request'" in t
            print("%-28s 迁移完成 | import request:%s 剩余axios.:%d" % (f, imp, remain))
        else:
            print("%-28s 跳过(已迁移/无裸axios)" % f)
    except Exception as e:
        print("%-28s 错误: %s" % (f, e))

print("\n完成")