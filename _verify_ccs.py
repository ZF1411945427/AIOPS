# -*- coding: utf-8 -*-
"""校验 component_catalog 拆分后门面完整性。"""
import app.services.mcp_tools  # noqa: F401 先触发引导导入顺序(绕开既有循环导入)
import app.services.component_catalog_service as ccs

syms = ['_BUILTIN_COMPONENTS', 'build_default_compose', '_inject_native_params',
        '_exec_ssh', 'full_health_check', '_ai_generate_plan', 'deploy_stream',
        'precheck_deploy', 'safe_json_parse', '_plan_to_visual_steps',
        'list_components', 'get_install', 'generate_install_report']

print("=== 门面符号完整性 ===")
ok = True
for sym in syms:
    found = hasattr(ccs, sym)
    if not found:
        ok = False
        print(f"  {sym}: MISSING")
    else:
        print(f"  {sym}: OK")

# 验证子模块互相引用
from app.services.component_catalog_ops import _install_to_dict
from app.services.component_catalog_ai import _ai_generate_plan
from app.services.component_catalog_render import native_deploy
from app.services.component_catalog_data import _BUILTIN_COMPONENTS
print("子模块独立 import OK")
print(f"内置组件数量: {len(_BUILTIN_COMPONENTS)}")

# 验证 ops 模块能访问 ai 的 _plan_to_visual_steps
from app.services.component_catalog_ops import _plan_to_visual_steps
print(f"_plan_to_visual_steps 可访问: {callable(_plan_to_visual_steps)}")

if ok:
    print("\n全部符号完整 ✅")
else:
    print("\n有缺失 ⚠️")