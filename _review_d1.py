# -*- coding: utf-8 -*-
"""D1 复查: 找出所有迁移后 request. 调用中被赋值的变量其后续 .data 引用(非解构语义残留)。
模式: const X = await request.Y(...) 后, 同一作用域内出现 X.data
简单启发: 找 "const <var> = await request." 的 var, 再统计该 var.data 出现次数。
"""
import io, re, glob

P = "frontend/src/views"
MIGRATED = ["ChaosScenarioView.vue", "ComponentStoreView.vue", "ConfigDriftView.vue",
            "ChaosReportView.vue", "ChaosExperimentView.vue", "InspectionView.vue",
            "ProvidersView.vue", "TenantManagementView.vue"]
# 剩余用全局 axios 的文件(无 import)
GLOBAL_AX = ["AvailabilityReportView.vue", "BurnRateView.vue", "ErrorBudgetView.vue",
             "OnCallView.vue", "SLAView.vue", "SLOConfigView.vue"]

for f in MIGRATED:
    path = P + "/" + f
    text = io.open(path, encoding="utf-8-sig").read()
    if "request" not in text:
        print("SKIP(无 request):", f); continue
    # 找 const <var> = await request.   (仅简单 var 名)
    issues = []
    for m in re.finditer(r"const\s+(\w+)\s*=\s*await\s+request\.\w+\([^)]*\)", text):
        var = m.group(1)
        # 统计该 var 后跟随 .data 的出现(排除反例)
        for dm in re.finditer(r"\b" + var + r"\.data\b", text):
            issues.append((m.group(0)[:50], dm.group(0)))
    # 也找 let X = await request./ await request. 直接式
    for m in re.finditer(r"\b(\w+)\s*=\s*await\s+request\.\w+\([^)]*\)", text):
        var = m.group(1)
        if var in ("data", "e", "ev", "val"):
            continue
        for dm in re.finditer(r"\b" + var + r"\.data\b", text[m.end():m.end()+400]):
            issues.append((m.group(0)[:45], dm.group(0)))
    if issues:
        print("== %s 风险 %d 处 ==" % (f, len(issues)))
        for a, b in issues[:15]:
            print("   assign:", a, "| use:", b)
    else:
        print("OK:", f, "无非解构 data 残留")

print("\n--- 6 个全局 axios 文件简要 ---")
for f in GLOBAL_AX:
    text = io.open(P + "/" + f, encoding="utf-8-sig").read()
    n = len(re.findall(r"\baxios\.", text))
    has_req = "import request from '@/api/request'" in text
    print(f, "| axios调用:", n, "| has request import:", has_req)
print("\n完成")
