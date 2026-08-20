# -*- coding: utf-8 -*-
"""D3 最小安全拆分: 把 FireMapView/ComponentStoreView 的 <style scoped> 块抽到独立 CSS 文件,
.vue 用 <style scoped src> 引入, 保留样式隔离, .vue 降到 <1500 行。"""
import io, os, re

os.chdir('frontend/src/views')
CWD = os.getcwd()  # frontend/src/views
TARGETS = [
    ("FireMapView.vue", "FireMapView.style.css"),
    ("ComponentStoreView.vue", "ComponentStoreView.style.css"),
]

for vue, css in TARGETS:
    text = io.open(vue, encoding="utf-8-sig").read()
    m = re.search(r"<style[^>]*>", text)
    if not m:
        print("跳过(无style):", vue); continue
    e = text.rfind("</style>")
    tag = m.group(0)               # <style scoped>
    style_content = text[m.end():e].rstrip() + "\n"
    # 写 CSS 文件(与 vue 同目录)
    with io.open(css, "w", encoding="utf-8", newline="") as f:
        f.write(style_content)
    # 替换 <style scoped>...内容...</style> 为 <style scoped src="./css"></style>
    new_block = tag[:tag.index(">")].replace(">", " src=\"./" + css + "\">") + "</style>"
    text = text[:m.start()] + tag[:tag.index(">")].replace(">", " src=\"./" + css + "\">") + "</style>" + text[e + len("</style>"):]
    io.open(vue, "w", encoding="utf-8", newline="").write(text)
    print("%s: style 抽到 %s, .vue 剩 %d 行" % (vue, css, text.count("\n") + 1))
print("完成")
