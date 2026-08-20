# -*- coding: utf-8 -*-
"""D1: 迁移 6 个 SRE view(原全局 axios, res.data 原生语义)到统一 request。
策略:
  1. 若无 request import, 在最后一个 import 之后插入 import request from '@/api/request'
  2. axios. -> request.
  3. 对 'const/let <var> = await request.X' 或 Promise.all 中赋值的变量,
     将 '<var>.data' 改为 '<var>'(因 request 拦截器已解包 response.data)。
     变量名通过匹配收集, 且排除 e/ev 等事件变量与 DOM 场景。
"""
import io, re

P = "frontend/src/views"
FILES = ["AvailabilityReportView.vue", "BurnRateView.vue", "ErrorBudgetView.vue",
         "OnCallView.vue", "SLAView.vue", "SLOConfigView.vue"]

def migrate(path):
    text = io.open(path, encoding="utf-8-sig").read()
    orig = text
    has_req = "import request from '@/api/request'" in text

    # 1. axios. -> request.
    if "axios." in text:
        text = text.replace("axios.", "request.")

    # 2. 收集被 request.X 赋值的变量(含 Promise.all 内直接 axios.get/request.get)
    assigned = set()
    # 模式 A: const/let <var> = await request.xxx(
    for m in re.finditer(r"\b(?:const|let)\s+(\w+)\s*=\s*await\s+request\.", text):
        assigned.add(m.group(1))
    # 模式 B: 顶层 await request.xxx( 作为 Promise 元素被赋值给变量(如 budgetRes/data)
    for m in re.finditer(r"\b(?:const|let)\s+(\w+)\s*=\s*request\.", text):
        assigned.add(m.group(1))
    # 模式 C: Promise.all([ ... request.xxx ...]) 内含赋值变量? 通过外层变量
    for m in re.finditer(r"(\w+)\s*=\s*await\s+request\.", text):
        assigned.add(m.group(1))

    # 只保留安全变量名(排除事件/DOM 变量, 避免误改 e.data / ev.data)
    skip = {"data", "e", "ev", "val", "ref"}
    # 注意: d / r / res 是 request 返回的 axios 变量, 其 .data 需去除, 故不放入 skip
    # 对每个 assigned 变量, 把 变量.data 改为 变量  (仅当确实出现在赋值后)
    for var in assigned:
        if var in skip:
            continue
        # 替换 <var>.data (不误伤 <var>.dataType 等? 只匹配 .data 后非字母)
        text = re.sub(r"\b" + re.escape(var) + r"\.data\b(?!\w)", var, text)

    # 若之前没有 request import, 插入 import
    if not has_req and "request." in text:
        # 在 <script... 块内最后一个 vue import 之后插入
        m = re.search(r"(<script[^>]*>\n(?:.*\n)*?)(\n)", text)
        lines = text.split("\n")
        # 找到最后一个 import line
        last_imp = -1
        for i, ln in enumerate(lines):
            if ln.strip().startswith("import ") and ln.strip().endswith("'"):
                last_imp = i
        if last_imp >= 0:
            lines.insert(last_imp + 1, "import request from '@/api/request'")
            text = "\n".join(lines)
        else:
            # 插到 <script 后
            mm = re.search(r"(<script[^>]*>)\n", text)
            if mm:
                text = text[:mm.end()] + "import request from '@/api/request'\n" + text[mm.end():]

    if text != orig:
        io.open(path, "w", encoding="utf-8", newline="").write(text)
    # 报告
    left = len(re.findall(r"\baxios", text))
    return "迁移完成 | 剩余axios字: %d | import request: %s" % (left, "import request from '@/api/request'" in text)

for f in FILES:
    try:
        print("%-28s %s" % (f, migrate(P + "/" + f)))
    except Exception as e:
        print("%-28s 错误: %s" % (f, e))
print("完成")
