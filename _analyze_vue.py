# -*- coding: utf-8 -*-
"""D3: 分析 4 个巨型 Vue 组件的 template/script/style 分区占比 + 顶层函数/常量数量。"""
import io, re

FILES = ["JarvisView.vue", "ComponentStoreView.vue", "FireMapView.vue", "DeployView.vue"]
P = "frontend/src/views/"

for f in FILES:
    text = io.open(P + f, encoding="utf-8-sig").read()
    total = text.count("\n") + 1
    tpl = re.search(r"<template>", text)
    tpl_end = re.search(r"</template>", text)
    scr = re.search(r"<script[^>]*>", text)
    scr_end = re.search(r"</script>", text)
    sty = re.search(r"<style", text)
    sty_end = re.search(r"</style>", text)
    def ln(m):
        return text[:m.start()].count("\n") + 1 if m else None
    tl = ln(tpl); tle = ln(tpl_end); sl = ln(scr); sle = ln(scr_end); yl = ln(sty); yle = ln(sty_end)
    # 计算各段行数
    tpl_rows = (tle - tl) if (tl and tle) else 0
    scr_rows = (sle - sl) if (sl and sle) else 0
    sty_rows = (yle - yl) if (yl and yle) else 0
    print("== %-28s 总 %d 行 ==" % (f, total))
    print("   template L%s-%s: %d 行 | script L%s-%s: %d 行 | style L%s-%s: %d 行" %
          (tl, tle, tpl_rows, sl, sle, scr_rows, yl, yle, sty_rows))
    # script 内顶层函数数量
    if sl and sle:
        sc = text[scr.end():scr_end.start()]
        funcs = re.findall(r"^(?:async\s+)?function\s+(\w+)|^const\s+(\w+)\s*=\s*(?:async\s*)?(?:\(.*\)|\w+)\s*=>", sc, re.M)
        consts = re.findall(r"^const\s+(\w+)\s*=", sc, re.M)
        print("   script 顶层函数/常量定义 %d 个: %s" % (len(consts), ", ".join(consts[:60])))
print("\n完成")
