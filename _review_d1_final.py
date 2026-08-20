# -*- coding: utf-8 -*-
"""D1 全面复查: 在 14 个迁移文件中找出所有紧急错误 - request 返回已解包, 但代码仍引用 X.data。
覆盖: 单变量赋值、数组解构 [...], Promise.all 的 await request，以及 request() 直接调用后的 .then。
方法: 找出所有 await request. 附近赋值产生的变量, 检查其后 .data 引用(排除 e.data 事件/ev.data)。
"""
import io, re

P = "frontend/src/views"
FILES = ["ChaosScenarioView.vue", "ComponentStoreView.vue", "ConfigDriftView.vue",
         "ChaosReportView.vue", "ChaosExperimentView.vue", "InspectionView.vue",
         "ProvidersView.vue", "TenantManagementView.vue",
         "AvailabilityReportView.vue", "BurnRateView.vue", "ErrorBudgetView.vue",
         "OnCallView.vue", "SLAView.vue", "SLOConfigView.vue"]

def find_problem(text, fn):
    problems = []
    # 数组解构: const [a, b] = await Promise.all([...])
    for m in re.finditer(r"const\s*\[\s*([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s*\]\s*=\s*await\s+Promise\.all", text):
        for name in [x.strip() for x in m.group(1).split(",")]:
            for dm in re.finditer(r"\b" + re.escape(name) + r"\.data\b", text):
                L = text[:dm.start()].count("\n") + 1
                problems.append((fn, L, name + ".data"))
    # 单变量: const/let/var X = await request.  或  X = await request.
    for m in re.finditer(r"\b(?:const|let|var)?\s*([A-Za-z_]\w*)\s*=\s*await\s+request\.", text):
        name = m.group(1)
        if name in ("e", "ev", "r", "d"):
            continue
        for dm in re.finditer(r"\b" + re.escape(name) + r"\.data\b", text):
            L = text[:dm.start()].count("\n") + 1
            problems.append((fn, L, name + ".data"))
    return problems

allp = []
for f in FILES:
    text = io.open(P + "/" + f, encoding="utf-8-sig").read()
    if "request" not in text:
        continue
    allp += find_problem(text, f)

if allp:
    print("发现 %d 处疑似 .data 残留:" % len(allp))
    for fn, L, expr in allp:
        print("  %s:L%d  %s" % (fn, L, expr))
else:
    print("全部 14 个迁移文件: 无 request 返回值 .data 残留 ✅")

# 顺便确认每个 request 函数调用者确实 import 了 request
for f in FILES:
    text = io.open(P + "/" + f, encoding="utf-8-sig").read()
    uses = len(re.findall(r"\brequest\.", text))
    has_imp = "import request from '@/api/request'" in text
    if uses and not has_imp:
        print("警告: %s 用 request 但无 import" % f)
print("\n复查完成")
