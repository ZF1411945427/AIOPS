# -*- coding: utf-8 -*-
"""deploy_service 拆分后门面完整性 + 调用链验证。"""
import app.services.mcp_tools  # noqa 先触发引导顺序(绕开既有循环导入)

import app.services.deploy_service as ds

print("=== 门面符号完整性 ===")
syms = [
    # 公共 API
    'probe_environment', 'ai_auto_env_mapping', 'ai_parse_manual', 'stop_execution',
    'release_exec_lock', 'create_plan', 'list_plans', 'get_plan', 'update_plan',
    'update_doc_raw', 'delete_plan', 'run_preflight', 'execute_plan', 'stream_execute',
    'resolve_env_mapping', 'stream_rollback_cleanup', 'submit_decision',
    'post_deploy_verify', 'generate_deploy_report', 'download_report',
    # 测试直接访问
    '_ai_autonomous_decision', '_ai_pre_execution_risk', '_ai_adaptive_rollback',
    '_ai_risk_scoring', 'detect_artifact_source', '_offline_blocked_reason',
    '_PUBLIC_REPO_HINTS', '_ai_diagnose_failure', '_extract_json', 'call_llm',
    'auto_download_artifact',
    # 私有执行链
    '_ai_stream_execute', '_stream_rollback', '_run_fix_commands',
    # 状态共享
    '_EXEC_LOCK', '_STOPPED', '_DECISIONS', '_STEP_TIMEOUT',
]
ok = True
for s in syms:
    found = hasattr(ds, s)
    if not found:
        ok = False
        print(f"  [MISSING] {s}")
for s in syms:
    if hasattr(ds, s):
        print(f"  [OK] {s}")

# 验证 mysql/monkeypatch 语义: 门面 call_llm 可被替换且 ai_engine 转发到门面
print("\n=== monkeypatch call_llm 转发验证 ===")
import app.services.deploy_ai_engine as die
orig_facade_llm = ds.call_llm
orig_engine_llm = die.call_llm
ds.call_llm = lambda *a, **k: {"__fake__": True}
# _DeferredCallLLM 应转发到门面当前值
fake = die.call_llm(provider=None, messages=[])
print(f"  ai_engine.call_llm 转发到门面 fake: {fake == {'__fake__': True}}")
ds.call_llm = orig_facade_llm

print("\n门面完整性:", "全部 OK ✅" if ok else "有缺失 ⚠️")