# -*- coding: utf-8 -*-
"""component_catalog_service.py 绞杀者拆分: 按函数边界精确切割。
生成 3 个子文件 + 主文件门面。备份原文件。不改函数体。
"""
import os
import shutil

SRC = "app/services/component_catalog_service.py"
BACKUP = "logs/component_catalog_service_backup_20260820.py"
os.makedirs("logs", exist_ok=True)
shutil.copy2(SRC, BACKUP)
print("备份:", BACKUP)

lines = open(SRC, encoding="utf-8").readlines()
total = len(lines)
print("原文件行数:", total)

# 函数/常量边界 (1-based 起始, 下一个顶层定义前结束). 通过源码扫描得到
import re
tops = []  # (line_no_1based, kind, name)
for i, ln in enumerate(lines):
    m = re.match(r"^(def|class) (\w+)", ln)
    if m:
        tops.append((i + 1, m.group(1), m.group(2)))
# 所有顶层定义的行号(含常量起点)
def _next_top_after(line_1based):
    """返回下一个顶层 def/class 的 1-based 行号, 或文件尾+1"""
    for ln, kind, name in tops:
        if ln > line_1based:
            return ln
    return len(lines) + 1

def block_range(start_1based):
    """从 start_1based 到下一个顶层 def/class 前, 去尾部空行"""
    end = _next_top_after(start_1based) - 1
    while end > start_1based and not lines[end - 1].strip():
        end -= 1
    return (start_1based, end)

# ── 分组 1: DATA (纯数据常量) ──
DATA_BLOCKS = [
    (30, "const"),      # _BUILTIN_COMPONENTS
    (765, "const"),     # _OFFLINE_PUBLIC_SOURCES
    (1755, "const"),    # _MIN_CVE_RULES
    (1989, "const"),    # _HEALTH_CMDS
    (1999, "const"),    # _CONFIG_FILES
    (2006, "const"),    # _NATIVE_VERIFY
    (2712, "const"),    # _SHELL_TRANSIENT_VARS
]
# ── 分组 2: RENDER (配方渲染/脚本生成 + 播种) ──
RENDER_BLOCKS = [
    (660, "def"),   # build_default_compose
    (677, "def"),   # _param_value
    (685, "def"),   # render_compose
    (755, "def"),   # _offline_native_block
    (772, "def"),   # _inject_native_params
    (820, "def"),   # _shell_quote
    (824, "def"),   # _stop_service
    (848, "def"),   # native_deploy
    (1240, "def"),  # seed_builtin_components
]
# ── 分组 3: AI (纯 AI 辅助, 不依赖主文件 CRUD/deploy_stream) ──
AI_BLOCKS = [
    (2412, "def"),  # _ai_decision_options
    (2455, "def"),  # _ai_intent_to_command
    (2486, "def"),  # _contains_cn
    (2490, "def"),  # _ai_generate_plan
    (2592, "def"),  # _plan_to_visual_steps
    (2635, "def"),  # _plan_step_kind
    (2651, "def"),  # _plan_to_steps
    (2686, "def"),  # _apply_plan_params
    (2706, "def"),  # _get_deploy_provider
    (2719, "def"),  # _extract_assignments
    (2745, "def"),  # _native_step_wrapper
    (2768, "def"),  # safe_json_parse
    (2794, "def"),  # _ai_autonomous_decision
    (2838, "def"),  # _rule_deploy_tip
    (2852, "def"),  # _ai_deploy_tip
    (2880, "def"),  # _ai_deploy_diagnosis
    (2921, "def"),  # _ai_final_report
    (3151, "def"),  # _build_install_report_key_points
]

def extract_blocks(blocks):
    out = []
    for start, kind in blocks:
        s, e = block_range(start)
        out.append((s, e))
    return out

def build_submodule(fname, blocks, extra_imports=""):
    out = []
    out.append('"""子模块(由 component_catalog 拆分生成, 勿手改函数体)"""\n')
    out.append("import json\nimport re\nimport socket\nimport base64\nimport time\nimport threading\n")
    out.append("from datetime import datetime\nfrom typing import Optional, List\n\n")
    out.append("from sqlalchemy.orm import Session\n\n")
    out.append("from app.models import Asset, ComponentCatalog, ComponentInstall\n")
    out.append("from app.routers.agent_sse import _clean_key_point\n\n")
    out.append("import logging\nlogger = logging.getLogger(__name__)\n\n")
    if extra_imports:
        out.append(extra_imports + "\n\n")
    for s, e in extract_blocks(blocks):
        out.append("# ─── 原 L%d-%d ───\n" % (s, e))
        out.extend(lines[s - 1:e])
        out.append("\n\n")
    content = "".join(out)
    with open(os.path.join("app/services", fname), "w", encoding="utf-8") as f:
        f.write(content)
    print("%s: %d 行" % (fname, content.count("\n")))

build_submodule("component_catalog_data.py", DATA_BLOCKS)
build_submodule("component_catalog_render.py", RENDER_BLOCKS,
                extra_imports=(
                    "from app.services.component_catalog_data import _OFFLINE_PUBLIC_SOURCES  # noqa\n"
                    "from app.services.component_catalog_data import _BUILTIN_COMPONENTS  # noqa\n"
                ))
# AI 子模块需要 render 的 build_default_compose/_inject_native_params
build_submodule("component_catalog_ai.py", AI_BLOCKS,
                extra_imports="from app.services.component_catalog_render import build_default_compose, _inject_native_params  # noqa")

print("子模块生成完成")