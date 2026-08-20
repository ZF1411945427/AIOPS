# -*- coding: utf-8 -*-
"""k8s 拆分后门面完整性 + 共享状态/循环导入验证。"""
import app.services.mcp_tools  # noqa 触发引导顺序(绕开既有循环导入)

import app.services.k8s_offline_deploy_service as svc

print("=== 门面符号完整性 ===")
syms = [
    # 公共 API
    'create_plan', 'get_plan', 'list_plans', 'update_plan', 'delete_plan',
    'stop_execution', 'run_deploy', 'submit_decision', 'validate_plan', 'precheck_plan',
    # router 用
    '_resolve_node_conn', '_create_platform_datasource',
    # 测试用状态/私有
    '_EXEC_LOCK', '_STOPPED', '_ACTIVE_CHANNELS', 'K8S_DECISIONS', '_TLOCAL',
    '_register_channel', '_unregister_channel', '_interrupt_plan_channels',
    # 编排
    '_run_deploy_generator', '_run_remote', '_sync_k8s_deploy_plan',
    '_k8s_preflight_ai', '_build_report', '_install_docker', '_k8s_ai_call',
]
ok = True
for s in syms:
    if not hasattr(svc, s):
        ok = False
        print(f"  [MISSING] {s}")
print(" 全部 %d 个目标符号%s" % (len(syms), "齐备 ✅" if ok else "有缺失 ⚠️"))

# 共享状态同一引用验证: 门面 _EXEC_LOCK 与 common _EXEC_LOCK 是同一 dict
from app.services import k8s_offline_common as kc
print("\n=== 共享状态同一引用 ===")
print(f"  _EXEC_LOCK 同一对象: {svc._EXEC_LOCK is kc._EXEC_LOCK}")
print(f"  _STOPPED 同一对象:   {svc._STOPPED is kc._STOPPED}")
print(f"  K8S_DECISIONS 同一:  {svc.K8S_DECISIONS is kc.K8S_DECISIONS}")

# 验证 _create_platform_datasource 类型(router 调用)
import types
print(f"\n  _create_platform_datasource callable: {callable(svc._create_platform_datasource)}")
print("\n门面完成:", "OK ✅" if ok else "⚠️")